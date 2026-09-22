"""Versioned, validated column-mapping document."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.imports.mapping.catalogue import TARGET_FIELDS


class DateTransform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["date", "datetime"]
    format: str | None = None
    timezone: str | None = None


class MoneyTransform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["money"]
    decimal_separator: Literal[".", ","] | None = None
    thousands_separator: Literal[".", ",", " "] | None = None

    @model_validator(mode="after")
    def separators_must_differ(self) -> MoneyTransform:
        if self.decimal_separator and self.decimal_separator == self.thousands_separator:
            raise ValueError("money separators must differ")
        return self


class BooleanTransform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["boolean"]
    true_values: tuple[str, ...] | None = None


class ValueMapTransform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["value_map"]
    map: dict[str, str]


Transform = Annotated[
    DateTransform | MoneyTransform | BooleanTransform | ValueMapTransform,
    Field(discriminator="type"),
]


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_column: str = Field(min_length=1)
    transform: Transform | None = None


class SkipFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    column: str = Field(min_length=1)
    operator: Literal["equals", "not_equals", "contains", "is_empty", "is_not_empty"]
    value: str | None = None

    @model_validator(mode="after")
    def value_required_for_comparison(self) -> SkipFilter:
        if self.operator in {"equals", "not_equals", "contains"} and self.value is None:
            raise ValueError(f"{self.operator} requires a value")
        return self


class MappingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1]
    fields: dict[str, FieldMapping]
    retain_unmapped: tuple[str, ...] = ()
    skip_rows_where: tuple[SkipFilter, ...] = ()

    @model_validator(mode="after")
    def valid_target_and_minimum_fields(self) -> MappingDocument:
        unknown = sorted(set(self.fields) - TARGET_FIELDS.keys())
        if unknown:
            raise ValueError(f"unknown target fields: {', '.join(unknown)}")
        if "service_date" not in self.fields:
            raise ValueError("service_date must be mapped")
        if not ({"customer_name", "customer_external_id"} & self.fields.keys()):
            raise ValueError("customer_name or customer_external_id must be mapped")
        return self

    def validate_source_columns(self, available: set[str]) -> None:
        referenced = {mapping.source_column for mapping in self.fields.values()}
        referenced.update(self.retain_unmapped)
        referenced.update(item.column for item in self.skip_rows_where)
        missing = sorted(referenced - available)
        if missing:
            raise ValueError(f"unknown source columns: {', '.join(missing)}")
