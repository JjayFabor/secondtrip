"""Human export-header synonyms for mapping suggestions."""

from typing import Final

SYNONYMS: Final[dict[str, frozenset[str]]] = {
    "external_job_id": frozenset({"job id", "work order", "work order id", "ticket id"}),
    "service_date": frozenset(
        {"service date", "completed date", "completion date", "job date", "date serviced"}
    ),
    "customer_name": frozenset(
        {
            "customer",
            "customer name",
            "client",
            "client name",
            "account name",
            "bill to",
            "customer_full_name",
            "cust name",
        }
    ),
    "customer_external_id": frozenset({"customer id", "client id", "account id"}),
    "customer_phone": frozenset({"phone", "customer phone", "telephone", "mobile"}),
    "customer_email": frozenset({"email", "customer email", "email address"}),
    "address_line1": frozenset({"address", "street", "street address", "service address"}),
    "city": frozenset({"city", "town"}),
    "region": frozenset({"state", "province", "region"}),
    "postal_code": frozenset({"zip", "zip code", "postal code", "postcode"}),
    "location_external_id": frozenset({"location id", "site id"}),
    "equipment_serial": frozenset({"serial", "serial number", "equipment serial"}),
    "equipment_manufacturer": frozenset({"manufacturer", "make", "equipment make"}),
    "equipment_model": frozenset({"model", "model number", "equipment model"}),
    "equipment_type": frozenset({"equipment type", "unit type", "asset type"}),
    "equipment_external_id": frozenset({"equipment id", "asset id", "unit id"}),
    "technician_name": frozenset({"technician", "tech", "technician name", "assigned tech"}),
    "technician_external_id": frozenset({"technician id", "tech id"}),
    "technician_code": frozenset({"technician code", "tech code", "employee code"}),
    "service_category": frozenset({"service category", "category", "business unit"}),
    "job_type": frozenset({"job type", "work type", "service type"}),
    "job_status": frozenset({"status", "job status", "work order status"}),
    "summary": frozenset({"summary", "job summary", "subject"}),
    "description": frozenset({"description", "job description", "details"}),
    "symptoms": frozenset({"symptoms", "complaint", "problem"}),
    "diagnosis": frozenset({"diagnosis", "diagnostic", "cause"}),
    "resolution": frozenset({"resolution", "repair", "work performed"}),
    "technician_notes": frozenset({"technician notes", "tech notes", "notes"}),
    "invoice_number": frozenset({"invoice", "invoice number", "invoice no"}),
    "revenue_amount": frozenset({"revenue", "invoice total", "total", "job total"}),
    "parts_amount": frozenset({"parts", "parts total", "parts amount"}),
    "labor_amount": frozenset({"labor", "labour", "labor total", "labor amount"}),
    "duration_minutes": frozenset({"duration", "duration minutes", "minutes", "job duration"}),
    "is_warranty": frozenset({"warranty", "warranty?", "is warranty"}),
    "warranty_reference": frozenset({"warranty reference", "warranty number"}),
    "scheduled_at": frozenset({"scheduled at", "scheduled date", "appointment"}),
    "started_at": frozenset({"started at", "start time", "arrival time"}),
    "completed_at": frozenset({"completed at", "completion time", "finished at"}),
}
