"""Tenant-scoped persistence for the import lifecycle."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, desc, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.ids import new_id
from app.core.pagination import decode_cursor, encode_cursor
from app.core.tenancy import TenantContext
from app.modules.imports.models import ImportBatch, ImportColumnMapping, ImportRow, ImportStatus


class ImportsRepository:
    def __init__(self, session: AsyncSession, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    async def get_batch(self, batch_id: UUID, *, for_update: bool = False) -> ImportBatch | None:
        statement = select(ImportBatch).where(
            ImportBatch.organization_id == self._tenant.organization_id,
            ImportBatch.id == batch_id,
            ImportBatch.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_batches(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[ImportBatch], str | None]:
        statement = select(ImportBatch).where(
            ImportBatch.organization_id == self._tenant.organization_id,
            ImportBatch.deleted_at.is_(None),
        )
        if cursor is not None:
            raw_created_at, cursor_id = decode_cursor(cursor)
            created_at = datetime.fromisoformat(str(raw_created_at).replace("Z", "+00:00"))
            statement = statement.where(
                or_(
                    ImportBatch.created_at < created_at,
                    and_(ImportBatch.created_at == created_at, ImportBatch.id < cursor_id),
                )
            )
        statement = statement.order_by(desc(ImportBatch.created_at), desc(ImportBatch.id)).limit(
            limit + 1
        )
        rows = list((await self._session.execute(statement)).scalars().all())
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            next_cursor = encode_cursor(sort_value=rows[-1].created_at, id=rows[-1].id)
        return rows, next_cursor

    async def create_batch(
        self,
        *,
        batch_id: UUID,
        source_system_id: UUID,
        created_by_user_id: UUID | None,
        original_filename: str,
        storage_key: str,
    ) -> ImportBatch:
        batch = ImportBatch(
            id=batch_id,
            organization_id=self._tenant.organization_id,
            source_system_id=source_system_id,
            created_by_user_id=created_by_user_id,
            original_filename=original_filename,
            storage_key=storage_key,
            status=ImportStatus.AWAITING_FILE,
        )
        self._session.add(batch)
        await self._session.flush()
        return batch

    async def find_original_by_hash(
        self, digest: bytes, *, excluding_batch_id: UUID
    ) -> ImportBatch | None:
        return (
            await self._session.execute(
                select(ImportBatch)
                .where(
                    ImportBatch.organization_id == self._tenant.organization_id,
                    ImportBatch.file_sha256 == digest,
                    ImportBatch.id != excluding_batch_id,
                    ImportBatch.deleted_at.is_(None),
                    ImportBatch.duplicate_of_batch_id.is_(None),
                )
                .order_by(ImportBatch.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def find_template_by_signature(
        self, signature: str, *, source_system_id: UUID
    ) -> ImportColumnMapping | None:
        return (
            await self._session.execute(
                select(ImportColumnMapping)
                .where(
                    ImportColumnMapping.organization_id == self._tenant.organization_id,
                    ImportColumnMapping.signature == signature,
                    or_(
                        ImportColumnMapping.source_system_id == source_system_id,
                        ImportColumnMapping.source_system_id.is_(None),
                    ),
                )
                .order_by(
                    ImportColumnMapping.is_default.desc(),
                    ImportColumnMapping.usage_count.desc(),
                    ImportColumnMapping.created_at.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_template(self, template_id: UUID) -> ImportColumnMapping | None:
        return (
            await self._session.execute(
                select(ImportColumnMapping).where(
                    ImportColumnMapping.organization_id == self._tenant.organization_id,
                    ImportColumnMapping.id == template_id,
                )
            )
        ).scalar_one_or_none()

    async def clear_validation_rows(self, batch_id: UUID) -> None:
        await self._session.execute(
            delete(ImportRow).where(
                ImportRow.organization_id == self._tenant.organization_id,
                ImportRow.import_batch_id == batch_id,
            )
        )

    async def existing_row_hashes(self, batch_id: UUID, hashes: list[bytes]) -> set[bytes]:
        if not hashes:
            return set()
        rows = await self._session.execute(
            select(ImportRow.row_hash).where(
                ImportRow.organization_id == self._tenant.organization_id,
                ImportRow.import_batch_id == batch_id,
                ImportRow.row_hash.in_(hashes),
            )
        )
        return set(rows.scalars().all())

    async def add_rows(self, rows: list[ImportRow]) -> None:
        if not rows:
            return
        await self._session.execute(
            insert(ImportRow),
            [
                {
                    "id": new_id(),
                    "organization_id": row.organization_id,
                    "import_batch_id": row.import_batch_id,
                    "row_number": row.row_number,
                    "raw_data": row.raw_data,
                    "normalized_data": row.normalized_data,
                    "row_hash": row.row_hash,
                    "status": row.status,
                    "issues": row.issues,
                    "job_id": row.job_id,
                }
                for row in rows
            ],
        )

    async def update_processed_rows(self, updates: list[dict[str, object]]) -> None:
        if not updates:
            return
        await self._session.execute(
            text(
                "UPDATE import_rows AS row SET "
                "status = data.status::import_row_status, "
                "issues = data.issues, job_id = data.job_id "
                "FROM jsonb_to_recordset(CAST(:updates AS jsonb)) "
                "AS data(id uuid, status text, issues jsonb, job_id uuid) "
                "WHERE row.organization_id = :organization_id AND row.id = data.id"
            ),
            {
                "organization_id": self._tenant.organization_id,
                "updates": json.dumps(updates),
            },
        )

    async def count_active_batches(self) -> int:
        value = await self._session.scalar(
            select(func.count())
            .select_from(ImportBatch)
            .where(
                ImportBatch.organization_id == self._tenant.organization_id,
                ImportBatch.status.in_({ImportStatus.QUEUED, ImportStatus.PROCESSING}),
                ImportBatch.deleted_at.is_(None),
            )
        )
        return int(value or 0)

    async def processing_rows(
        self,
        batch_id: UUID,
        *,
        first_row_number: int,
        processed_rows: int,
        limit: int,
    ) -> list[ImportRow]:
        return list(
            (
                await self._session.execute(
                    select(ImportRow)
                    .options(
                        load_only(
                            ImportRow.id,
                            ImportRow.row_number,
                            ImportRow.row_hash,
                            ImportRow.status,
                            ImportRow.issues,
                            ImportRow.normalized_data,
                        )
                    )
                    .where(
                        ImportRow.organization_id == self._tenant.organization_id,
                        ImportRow.import_batch_id == batch_id,
                        ImportRow.row_number >= first_row_number + processed_rows,
                    )
                    .order_by(ImportRow.row_number)
                    .limit(limit)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    async def raw_data_for_rows(self, row_ids: list[UUID]) -> dict[UUID, dict[str, object]]:
        if not row_ids:
            return {}
        rows = (
            await self._session.execute(
                select(ImportRow.id, ImportRow.raw_data).where(
                    ImportRow.organization_id == self._tenant.organization_id,
                    ImportRow.id.in_(row_ids),
                )
            )
        ).all()
        return {row_id: raw_data for row_id, raw_data in rows}

    async def sample_source_values(
        self,
        batch_id: UUID,
        *,
        source_column: str,
        limit: int = 200,
    ) -> list[str]:
        rows = (
            await self._session.execute(
                select(ImportRow.raw_data)
                .where(
                    ImportRow.organization_id == self._tenant.organization_id,
                    ImportRow.import_batch_id == batch_id,
                )
                .order_by(ImportRow.row_number)
                .limit(limit)
            )
        ).scalars()
        return [str(row.get(source_column, "")) for row in rows]

    async def list_issue_rows(
        self,
        batch_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ImportRow], str | None]:
        statement = select(ImportRow).where(
            ImportRow.organization_id == self._tenant.organization_id,
            ImportRow.import_batch_id == batch_id,
            func.jsonb_array_length(ImportRow.issues) > 0,
        )
        if cursor is not None:
            raw_row_number, cursor_id = decode_cursor(cursor)
            row_number = int(raw_row_number)
            statement = statement.where(
                or_(
                    ImportRow.row_number > row_number,
                    and_(ImportRow.row_number == row_number, ImportRow.id > cursor_id),
                )
            )
        statement = statement.order_by(ImportRow.row_number, ImportRow.id).limit(limit + 1)
        rows = list((await self._session.execute(statement)).scalars().all())
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            next_cursor = encode_cursor(sort_value=rows[-1].row_number, id=rows[-1].id)
        return rows, next_cursor
