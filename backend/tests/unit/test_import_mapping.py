from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.imports.mapping.catalogue import TARGET_FIELDS
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.mapping.suggester import (
    SuggestionStrategy,
    mapping_signature,
    suggest_mappings,
)
from app.modules.imports.profiling import ColumnProfile, InferredType


def test_catalogue_has_architecture_required_fields() -> None:
    assert len(TARGET_FIELDS) == 38
    assert TARGET_FIELDS["service_date"].required is True
    assert {"customer_name", "customer_external_id", "equipment_serial", "resolution"} <= (
        TARGET_FIELDS.keys()
    )


def test_mapping_document_requires_minimum_viable_import() -> None:
    document = MappingDocument.model_validate(
        {
            "version": 1,
            "fields": {
                "service_date": {"source_column": "Completed Date"},
                "customer_external_id": {"source_column": "Customer ID"},
            },
            "retain_unmapped": ["Lead Source"],
            "skip_rows_where": [{"column": "Status", "operator": "equals", "value": "Estimate"}],
        }
    )
    document.validate_source_columns({"Completed Date", "Customer ID", "Lead Source", "Status"})

    with pytest.raises(ValidationError, match="service_date"):
        MappingDocument.model_validate(
            {"version": 1, "fields": {"customer_name": {"source_column": "Customer"}}}
        )
    with pytest.raises(ValidationError, match="customer_name or customer_external_id"):
        MappingDocument.model_validate(
            {"version": 1, "fields": {"service_date": {"source_column": "Date"}}}
        )
    with pytest.raises(ValidationError, match="unknown target"):
        MappingDocument.model_validate(
            {
                "version": 1,
                "fields": {
                    "service_date": {"source_column": "Date"},
                    "customer_name": {"source_column": "Customer"},
                    "invented": {"source_column": "Nope"},
                },
            }
        )


def test_mapping_document_rejects_unknown_source_columns() -> None:
    document = MappingDocument.model_validate(
        {
            "version": 1,
            "fields": {
                "service_date": {"source_column": "Date"},
                "customer_name": {"source_column": "Missing"},
            },
        }
    )
    with pytest.raises(ValueError, match="Missing"):
        document.validate_source_columns({"Date"})


def test_mapping_signature_is_case_and_order_insensitive() -> None:
    assert mapping_signature([" Customer ", "SERVICE DATE"]) == mapping_signature(
        ["service date", "customer"]
    )
    assert mapping_signature(["customer", "customer"]) != mapping_signature(["customer"])


def test_suggestions_use_synonyms_then_type_checked_fuzzy_matching() -> None:
    columns = (
        ColumnProfile("Client Name", 0, ("Acme",), InferredType.TEXT),
        ColumnProfile("Servce Date", 1, ("2026-09-18",), InferredType.DATE),
        ColumnProfile("Invoce Total", 2, ("123.45",), InferredType.MONEY),
    )
    suggestions = suggest_mappings(columns)
    by_source = {suggestion.source_column: suggestion for suggestion in suggestions}

    assert by_source["Client Name"].target_field == "customer_name"
    assert by_source["Client Name"].strategy is SuggestionStrategy.SYNONYM
    assert by_source["Servce Date"].target_field == "service_date"
    assert by_source["Servce Date"].strategy is SuggestionStrategy.FUZZY
    assert by_source["Invoce Total"].target_field == "revenue_amount"

    incompatible = suggest_mappings(
        (ColumnProfile("Servce Date", 0, ("not a date",), InferredType.TEXT),)
    )
    assert incompatible == ()
