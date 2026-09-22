"""Deterministic, fictional HVAC CSV fixtures shared by local tooling."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.modules.imports.mapping.document import MappingDocument

FIXTURE_VERSION = "hvac-v2"

COLUMNS = (
    "Job ID",
    "Customer ID",
    "Customer",
    "Phone",
    "Email",
    "Date",
    "Location ID",
    "Address",
    "City",
    "Region",
    "Postal",
    "Equipment ID",
    "Serial",
    "Manufacturer",
    "Model",
    "Equipment Type",
    "Technician",
    "Tech Code",
    "Category",
    "Job Type",
    "Status",
    "Summary",
    "Description",
    "Symptoms",
    "Diagnosis",
    "Resolution",
    "Notes",
    "Invoice",
    "Revenue",
    "Parts",
    "Labor",
    "Duration",
    "Warranty",
    "Warranty Reference",
    "Scheduled At",
    "Started At",
    "Completed At",
    "Contract Type",
    "Zone",
)


MAPPING = MappingDocument.model_validate(
    {
        "version": 1,
        "fields": {
            "external_job_id": {"source_column": "Job ID"},
            "customer_external_id": {"source_column": "Customer ID"},
            "customer_name": {"source_column": "Customer"},
            "customer_phone": {"source_column": "Phone"},
            "customer_email": {"source_column": "Email"},
            "service_date": {"source_column": "Date"},
            "location_external_id": {"source_column": "Location ID"},
            "address_line1": {"source_column": "Address"},
            "city": {"source_column": "City"},
            "region": {"source_column": "Region"},
            "postal_code": {"source_column": "Postal"},
            "equipment_external_id": {"source_column": "Equipment ID"},
            "equipment_serial": {"source_column": "Serial"},
            "equipment_manufacturer": {"source_column": "Manufacturer"},
            "equipment_model": {"source_column": "Model"},
            "equipment_type": {"source_column": "Equipment Type"},
            "technician_name": {"source_column": "Technician"},
            "technician_code": {"source_column": "Tech Code"},
            "service_category": {"source_column": "Category"},
            "job_type": {"source_column": "Job Type"},
            "job_status": {
                "source_column": "Status",
                "transform": {"type": "value_map", "map": {"Closed": "completed"}},
            },
            "summary": {"source_column": "Summary"},
            "description": {"source_column": "Description"},
            "symptoms": {"source_column": "Symptoms"},
            "diagnosis": {"source_column": "Diagnosis"},
            "resolution": {"source_column": "Resolution"},
            "technician_notes": {"source_column": "Notes"},
            "invoice_number": {"source_column": "Invoice"},
            "revenue_amount": {"source_column": "Revenue"},
            "parts_amount": {"source_column": "Parts"},
            "labor_amount": {"source_column": "Labor"},
            "duration_minutes": {"source_column": "Duration"},
            "is_warranty": {
                "source_column": "Warranty",
                "transform": {"type": "boolean", "true_values": ["Y"]},
            },
            "warranty_reference": {"source_column": "Warranty Reference"},
            "scheduled_at": {"source_column": "Scheduled At"},
            "started_at": {"source_column": "Started At"},
            "completed_at": {"source_column": "Completed At"},
        },
        "retain_unmapped": ["Contract Type", "Zone"],
    }
)


@dataclass(frozen=True, slots=True)
class CsvFixture:
    body: bytes
    rows: int
    sha256: str


def render_csv(rows: Iterable[dict[str, str]]) -> CsvFixture:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    count = 0
    for row in rows:
        writer.writerow(row)
        count += 1
    body = stream.getvalue().encode("utf-8")
    return CsvFixture(body=body, rows=count, sha256=hashlib.sha256(body).hexdigest())


def performance_rows(row_count: int) -> Iterator[dict[str, str]]:
    if row_count < 1:
        raise ValueError("row_count must be positive")
    base = date(2022, 1, 3)
    technicians = (
        "Alex Rivera",
        "Morgan Lee",
        "Jordan Patel",
        "Casey Brooks",
        "Taylor Nguyen",
    )
    categories = (
        "Cooling",
        "Heating",
        "Repair",
        "Maintenance",
        "Installation",
        "Indoor Air Quality",
        "Controls",
        "Ventilation",
    )
    for index in range(row_count):
        customer = index // 5
        visit = index % 5
        service_date = base + timedelta(days=(customer * 11 + visit * 47) % 1460)
        technician_index = index % 25
        technician = f"{technicians[technician_index % len(technicians)]} {technician_index + 1}"
        has_equipment = customer % 10 != 0
        warranty = index % 97 == 0
        category = categories[index % len(categories)]
        revenue = Decimal("0.00") if warranty else Decimal("185.00") + Decimal(index % 700)
        yield _row(
            job_id=f"PERF-{index + 1:06d}",
            customer_ordinal=customer,
            service_date=service_date,
            technician=technician,
            technician_code=f"T-{technician_index + 1:02d}",
            category=category,
            summary=f"{category} service",
            description="HVAC service requested.",
            symptoms="Comfort issue.",
            diagnosis="HVAC fault confirmed.",
            resolution="Service completed.",
            notes=("Recorded final operating condition." if index % 10 == 0 else ""),
            revenue=revenue,
            warranty=warranty,
            has_equipment=has_equipment,
            contract_type="Residential service",
            zone=f"Zone {(customer % 12) + 1}",
        )


def demo_rows() -> Iterator[dict[str, str]]:
    ordinal = 0
    base = date(2025, 3, 3)
    for kind, pair_count in (
        ("callback", 12),
        ("scheduled_maintenance", 8),
        ("planned_multivisit", 4),
        ("unrelated", 8),
    ):
        for pair in range(pair_count):
            customer = ordinal
            ordinal += 1
            first_date = base + timedelta(days=customer * 13)
            prior_id = demo_pair_job_id(kind, pair, "A")
            followup_id = demo_pair_job_id(kind, pair, "B")
            technician = "Alex Rivera" if pair % 2 == 0 else "Morgan Lee"
            technician_code = "T-01" if pair % 2 == 0 else "T-02"
            has_equipment = pair % 5 != 0
            zone = f"Zone {(pair % 4) + 1}"
            yield _row(
                job_id=prior_id,
                service_date=first_date,
                category="Maintenance" if kind == "scheduled_maintenance" else "Repair",
                summary=(
                    "Annual cooling tune-up" if kind == "scheduled_maintenance" else "No cooling"
                ),
                description="System was not maintaining the requested indoor temperature.",
                symptoms="Warm air and long compressor run time.",
                diagnosis="Low refrigerant charge and a loose electrical connection.",
                resolution="Corrected charge, secured connection, and verified cooling.",
                notes="Documented baseline readings before departure.",
                revenue=Decimal("395.00"),
                warranty=False,
                contract_type=(
                    "Planned multi-visit project"
                    if kind == "planned_multivisit"
                    else "Residential service"
                ),
                customer_ordinal=customer,
                technician=technician,
                technician_code=technician_code,
                has_equipment=has_equipment,
                zone=zone,
            )
            if kind == "callback":
                details = (
                    "Repair",
                    "Still not cooling",
                    "Customer reported the same cooling problem after the prior visit.",
                    "Warm air returned after several days.",
                    "Original electrical repair did not hold under load.",
                    "Completed warranty correction and verified operation.",
                    Decimal("0.00"),
                    True,
                    4,
                )
            elif kind == "scheduled_maintenance":
                details = (
                    "Maintenance",
                    "Seasonal heating tune-up",
                    "Scheduled contract maintenance for the upcoming heating season.",
                    "No active complaint; routine inspection requested.",
                    "Normal wear only.",
                    "Completed scheduled maintenance checklist.",
                    Decimal("149.00"),
                    False,
                    21,
                )
            elif kind == "planned_multivisit":
                details = (
                    "Installation",
                    "Complete planned equipment installation",
                    "Second scheduled visit for a planned two-stage installation.",
                    "No failure; return visit was planned for final commissioning.",
                    "Project phase two.",
                    "Commissioned equipment and closed planned project.",
                    Decimal("2200.00"),
                    False,
                    1,
                )
            else:
                details = (
                    "Indoor air quality",
                    "Install air purifier",
                    "Customer requested an unrelated indoor-air-quality upgrade.",
                    "Seasonal allergy concerns, unrelated to cooling repair.",
                    "Existing HVAC repair remained operational.",
                    "Installed purifier and reviewed filter replacement.",
                    Decimal("875.00"),
                    False,
                    12,
                )
            (
                category,
                summary,
                description,
                symptoms,
                diagnosis,
                resolution,
                revenue,
                warranty,
                gap,
            ) = details
            yield _row(
                job_id=followup_id,
                service_date=first_date + timedelta(days=gap),
                category=category,
                summary=summary,
                description=description,
                symptoms=symptoms,
                diagnosis=diagnosis,
                resolution=resolution,
                notes="Follow-up visit completed and customer advised.",
                revenue=revenue,
                warranty=warranty,
                contract_type=(
                    "Planned multi-visit project"
                    if kind == "planned_multivisit"
                    else "Residential service"
                ),
                customer_ordinal=customer,
                technician="Jordan Patel" if kind == "unrelated" else technician,
                technician_code="T-03" if kind == "unrelated" else technician_code,
                has_equipment=has_equipment,
                zone=zone,
                visit_variant="-B" if kind == "unrelated" else "",
            )
    for noise in range(32):
        customer = ordinal
        ordinal += 1
        yield _row(
            job_id=f"DEMO-NOISE-{noise + 1:02d}",
            customer_ordinal=customer,
            service_date=base + timedelta(days=(noise * 17) % 500),
            technician="Jordan Patel",
            technician_code="T-03",
            category=("Repair", "Maintenance", "Installation")[noise % 3],
            summary=("Replace blower capacitor", "Annual maintenance", "Install thermostat")[
                noise % 3
            ],
            description="Standalone fictional HVAC service visit.",
            symptoms="Customer requested service for a distinct issue.",
            diagnosis="Inspection confirmed a single isolated condition.",
            resolution="Completed work and verified normal operation.",
            notes="No related return visit in the demo window.",
            revenue=Decimal("275.00") + Decimal(noise * 11),
            warranty=noise % 11 == 0,
            has_equipment=noise % 7 != 0,
            contract_type="Residential service",
            zone=f"Zone {(noise % 4) + 1}",
        )


def demo_pair_job_id(kind: str, index: int, side: str) -> str:
    prefixes = {
        "callback": "CB",
        "scheduled_maintenance": "MAINT",
        "planned_multivisit": "PLAN",
        "unrelated": "UNREL",
    }
    return f"DEMO-{prefixes[kind]}-{index + 1:02d}-{side}"


def _row(
    *,
    job_id: str,
    customer_ordinal: int,
    service_date: date,
    technician: str,
    technician_code: str,
    category: str,
    summary: str,
    description: str,
    symptoms: str,
    diagnosis: str,
    resolution: str,
    notes: str,
    revenue: Decimal,
    warranty: bool,
    has_equipment: bool,
    contract_type: str,
    zone: str,
    visit_variant: str = "",
) -> dict[str, str]:
    customer_number = customer_ordinal + 1
    start = datetime.combine(service_date, time(9, 0))
    end = start + timedelta(minutes=90)
    equipment_id = f"EQ-{customer_number:05d}{visit_variant}" if has_equipment else ""
    serial = f"HVAC-{customer_number:07d}{visit_variant}" if has_equipment else ""
    parts = Decimal("0.00") if warranty else (revenue * Decimal("0.35")).quantize(Decimal("0.01"))
    labor = Decimal("0.00") if warranty else (revenue - parts).quantize(Decimal("0.01"))
    return {
        "Job ID": job_id,
        "Customer ID": f"C-{customer_number:05d}",
        "Customer": f"Fictional Customer {customer_number:05d}",
        "Phone": f"+1212{1000000 + customer_ordinal:07d}",
        "Email": f"customer{customer_number:05d}@example.test",
        "Date": service_date.isoformat(),
        "Location ID": f"L-{customer_number:05d}{visit_variant}",
        "Address": f"{100 + customer_number} Example Avenue{visit_variant}",
        "City": "Riverton",
        "Region": "IL",
        "Postal": f"{60000 + customer_ordinal % 9999:05d}",
        "Equipment ID": equipment_id,
        "Serial": serial,
        "Manufacturer": "Carrier" if has_equipment else "",
        "Model": "24ACC6" if has_equipment else "",
        "Equipment Type": "Split system" if has_equipment else "",
        "Technician": technician,
        "Tech Code": technician_code,
        "Category": category,
        "Job Type": "Service",
        "Status": "Closed",
        "Summary": summary,
        "Description": description,
        "Symptoms": symptoms,
        "Diagnosis": diagnosis,
        "Resolution": resolution,
        "Notes": notes,
        "Invoice": f"INV-{job_id}",
        "Revenue": f"{revenue:.2f}",
        "Parts": f"{parts:.2f}",
        "Labor": f"{labor:.2f}",
        "Duration": "90",
        "Warranty": "Y" if warranty else "N",
        "Warranty Reference": f"WR-{job_id}" if warranty else "",
        "Scheduled At": (start - timedelta(days=2)).isoformat(),
        "Started At": start.isoformat(),
        "Completed At": end.isoformat(),
        "Contract Type": contract_type,
        "Zone": zone,
    }
