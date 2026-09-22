"use client";

import { useEffect, useState } from "react";
import { FileUp } from "lucide-react";
import Link from "next/link";

import { useAppShell } from "@/components/dashboard/app-shell";
import {
  formatDateTime,
  ImportPageHeader,
  ImportStatusBadge,
} from "@/components/imports/import-ui";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, getApiErrorMessage, type ImportList } from "@/lib/api";

export function ImportListView({
  initialOrganizationId,
  initialPage,
  initialError,
}: {
  initialOrganizationId?: string;
  initialPage?: ImportList;
  initialError?: string;
}) {
  const { organization, canManageImports } = useAppShell();
  const [page, setPage] = useState<ImportList | undefined>(initialPage);
  const [pageOrganizationId, setPageOrganizationId] = useState<string | undefined>(
    initialOrganizationId,
  );
  const [cursor, setCursor] = useState<string>();
  const [cursorHistory, setCursorHistory] = useState<(string | undefined)[]>([]);
  const [cursorOrganizationId, setCursorOrganizationId] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>(initialError);
  const [reloadRequest, setReloadRequest] = useState(0);
  const paginationMatchesOrganization = cursorOrganizationId === organization?.id;
  const activeCursor = paginationMatchesOrganization ? cursor : undefined;
  const activeCursorHistory = paginationMatchesOrganization ? cursorHistory : [];

  useEffect(() => {
    if (!organization) return;
    if (
      organization.id === initialOrganizationId &&
      activeCursor === undefined &&
      reloadRequest === 0
    ) {
      return;
    }
    let active = true;
    api.listImports(organization.id, { cursor: activeCursor, limit: 25 })
      .then((result) => {
        if (!active) return;
        setPage(result);
        setPageOrganizationId(organization.id);
        setError(undefined);
      })
      .catch((requestError: unknown) => {
        if (active) setError(getApiErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [activeCursor, initialOrganizationId, organization, reloadRequest]);

  const newImportHref = organization
    ? `/app/imports/new?org=${encodeURIComponent(organization.id)}`
    : "/app/imports/new";

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <ImportPageHeader
        title="Imports"
        description="Track every CSV from upload through validation and processing. Counts stay attached to the source file so nothing disappears silently."
        action={canManageImports ? <Button asChild><Link href={newImportHref}>Import jobs</Link></Button> : undefined}
      />

      {!organization ? (
        <Card className="p-6"><h2 className="text-lg font-semibold text-text-primary">No workspace selected</h2><p className="mt-2 text-sm text-text-secondary">Create or join an organization before importing job history.</p></Card>
      ) : loading || (pageOrganizationId !== organization.id && !error) ? (
        <ImportListLoading />
      ) : error ? (
        <Card className="border-danger bg-[var(--danger-bg)] p-5" role="alert">
          <p className="font-semibold text-danger">Import history is unavailable</p>
          <p className="mt-1 text-sm text-text-primary">{error}</p>
          <Button className="mt-4" variant="secondary" onClick={() => { setLoading(true); setError(undefined); setReloadRequest((value) => value + 1); }}>Try again</Button>
        </Card>
      ) : !page?.data.length ? (
        <Card className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
          <FileUp size={20} strokeWidth={1.75} className="text-brand-primary" aria-hidden="true" />
          <h2 className="mt-4 text-lg font-semibold text-text-primary">No import history yet</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-text-secondary">
            Import job history to begin checking the file, mapping columns, and reviewing row issues.
          </p>
          {canManageImports && <Button asChild className="mt-5"><Link href={newImportHref}>Import jobs</Link></Button>}
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <Table className="min-w-[900px]" scrollLabel="Import history">
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead align="right">Rows</TableHead>
                  <TableHead align="right">Jobs created</TableHead>
                  <TableHead align="right">Jobs updated</TableHead>
                  <TableHead align="right">Errors</TableHead>
                  <TableHead>Created at</TableHead>
                  <TableHead><span className="sr-only">Open</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.data.map((batch) => (
                  <TableRow key={batch.id}>
                    <TableCell>
                      <p className="max-w-72 truncate font-medium" title={batch.original_filename ?? "Untitled import"}>
                        {batch.original_filename ?? "Untitled import"}
                      </p>
                      <p className="mt-0.5 text-xs text-text-secondary">{batch.id}</p>
                    </TableCell>
                    <TableCell><ImportStatusBadge status={batch.status} /></TableCell>
                    <TableCell align="right">{batch.total_rows.toLocaleString()}</TableCell>
                    <TableCell align="right">{batch.created_jobs.toLocaleString()}</TableCell>
                    <TableCell align="right">{batch.updated_jobs.toLocaleString()}</TableCell>
                    <TableCell align="right">{batch.error_rows.toLocaleString()}</TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {formatDateTime(batch.created_at, organization?.timezone ?? "UTC")}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/app/imports/${batch.id}?org=${encodeURIComponent(batch.organization_id)}`}
                        className="font-semibold text-brand-primary underline-offset-4 hover:underline"
                        aria-label={`Open import ${batch.original_filename ?? batch.id}`}
                      >
                        View
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <nav className="flex items-center justify-between" aria-label="Import history pagination">
            <Button
              variant="secondary"
              disabled={!activeCursorHistory.length}
              onClick={() => {
                const previous = activeCursorHistory.at(-1);
                setLoading(true);
                setCursorOrganizationId(organization?.id);
                setCursorHistory(activeCursorHistory.slice(0, -1));
                setCursor(previous);
              }}
            >
              Previous
            </Button>
            <span className="text-sm text-text-secondary">{page.data.length} imports on this page</span>
            <Button
              variant="secondary"
              disabled={!page.page.has_more || !page.page.next_cursor}
              onClick={() => {
                setLoading(true);
                setCursorOrganizationId(organization?.id);
                setCursorHistory([...activeCursorHistory, activeCursor]);
                setCursor(page.page.next_cursor ?? undefined);
              }}
            >
              Next
            </Button>
          </nav>
        </>
      )}
    </div>
  );
}

function ImportListLoading() {
  return (
    <div className="space-y-3" aria-label="Loading import history">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-14 w-full" />
    </div>
  );
}
