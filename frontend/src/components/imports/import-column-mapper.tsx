"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  getApiErrorMessage,
  type ImportBatch,
  type ImportFieldMapping,
  type ImportMappingDocument,
  type ImportPreview,
  type ValueMapTransform,
} from "@/lib/api";

interface TargetField {
  key: string;
  label: string;
  required?: boolean;
}

const FIELD_GROUPS: { label: string; fields: TargetField[] }[] = [
  {
    label: "Job",
    fields: [
      { key: "external_job_id", label: "External job ID" },
      { key: "service_date", label: "Service date", required: true },
      { key: "job_status", label: "Job status" },
      { key: "service_category", label: "Service category" },
      { key: "job_type", label: "Job type" },
      { key: "summary", label: "Summary" },
      { key: "description", label: "Description" },
    ],
  },
  {
    label: "Customer & location",
    fields: [
      { key: "customer_name", label: "Customer name" },
      { key: "customer_external_id", label: "Customer external ID" },
      { key: "customer_phone", label: "Customer phone" },
      { key: "customer_email", label: "Customer email" },
      { key: "location_external_id", label: "Location external ID" },
      { key: "address_line1", label: "Address line 1" },
      { key: "city", label: "City" },
      { key: "region", label: "Region" },
      { key: "postal_code", label: "Postal code" },
    ],
  },
  {
    label: "Equipment",
    fields: [
      { key: "equipment_external_id", label: "Equipment external ID" },
      { key: "equipment_serial", label: "Equipment serial" },
      { key: "equipment_manufacturer", label: "Equipment manufacturer" },
      { key: "equipment_model", label: "Equipment model" },
      { key: "equipment_type", label: "Equipment type" },
    ],
  },
  {
    label: "Technician",
    fields: [
      { key: "technician_name", label: "Technician name" },
      { key: "technician_external_id", label: "Technician external ID" },
      { key: "technician_code", label: "Technician code" },
    ],
  },
  {
    label: "Financial & detail",
    fields: [
      { key: "symptoms", label: "Symptoms" },
      { key: "diagnosis", label: "Diagnosis" },
      { key: "resolution", label: "Resolution" },
      { key: "technician_notes", label: "Technician notes" },
      { key: "invoice_number", label: "Invoice number" },
      { key: "revenue_amount", label: "Revenue amount" },
      { key: "parts_amount", label: "Parts amount" },
      { key: "labor_amount", label: "Labor amount" },
      { key: "duration_minutes", label: "Duration in minutes" },
      { key: "is_warranty", label: "Warranty flag" },
      { key: "warranty_reference", label: "Warranty reference" },
      { key: "scheduled_at", label: "Scheduled at" },
      { key: "started_at", label: "Started at" },
      { key: "completed_at", label: "Completed at" },
    ],
  },
];

const TARGET_LABELS = Object.fromEntries(
  FIELD_GROUPS.flatMap((group) => group.fields.map((field) => [field.key, field.label])),
);
const UNMAPPED = "__unmapped__";

function initialFields(batch: ImportBatch, preview: ImportPreview): Record<string, ImportFieldMapping> {
  if (batch.mapping) return structuredClone(batch.mapping.fields);
  if (preview.suggested_mapping) return structuredClone(preview.suggested_mapping.fields);
  return Object.fromEntries(
    preview.suggestions.map((suggestion) => [suggestion.target_field, { source_column: suggestion.source_column }]),
  );
}

export function ImportColumnMapper({
  organizationId,
  batch,
  preview,
  onBatchChange,
}: {
  organizationId: string;
  batch: ImportBatch;
  preview: ImportPreview;
  onBatchChange: (batch: ImportBatch) => void;
}) {
  const [fields, setFields] = useState<Record<string, ImportFieldMapping>>(() => initialFields(batch, preview));
  const [retained, setRetained] = useState<string[]>(() => batch.mapping?.retain_unmapped ?? preview.suggested_mapping?.retain_unmapped ?? []);
  const [statusMap, setStatusMap] = useState(() => {
    const transform = initialFields(batch, preview).job_status?.transform;
    if (transform?.type !== "value_map") return "";
    return Object.entries(transform.map).map(([source, target]) => `${source}=${target}`).join("\n");
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState("Review every suggested match before validating the file.");

  const assignedSources = useMemo(
    () => new Set(Object.values(fields).map((field) => field.source_column)),
    [fields],
  );
  const sourceToTarget = useMemo(
    () => Object.fromEntries(Object.entries(fields).map(([target, mapping]) => [mapping.source_column, target])),
    [fields],
  );
  const unmappedColumns = preview.columns.filter((column) => !assignedSources.has(column.name));
  const validationMessages: string[] = [];
  if (!fields.service_date) validationMessages.push("Map a source column to Service date.");
  if (!fields.customer_name && !fields.customer_external_id) {
    validationMessages.push("Map Customer name or Customer external ID.");
  }

  function updateField(target: string, source: string) {
    setError(undefined);
    setFields((current) => {
      const next = { ...current };
      if (source === UNMAPPED) {
        delete next[target];
        return next;
      }
      next[target] = { ...current[target], source_column: source };
      return next;
    });
    setRetained((current) => current.filter((column) => column !== source));
  }

  function parseStatusMap(): ValueMapTransform | undefined {
    const map: Record<string, string> = {};
    for (const [index, line] of statusMap.split("\n").entries()) {
      if (!line.trim()) continue;
      const separator = line.indexOf("=");
      if (separator <= 0 || !line.slice(separator + 1).trim()) {
        throw new Error(`Job status map line ${index + 1} must use source=destination.`);
      }
      map[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
    }
    return Object.keys(map).length ? { type: "value_map", map } : undefined;
  }

  async function saveAndValidate() {
    if (validationMessages.length) {
      setError(validationMessages.join(" "));
      return;
    }
    setSaving(true);
    setError(undefined);
    setMessage("Saving the mapping…");
    try {
      const nextFields = structuredClone(fields);
      if (nextFields.job_status) {
        const existing = nextFields.job_status.transform;
        const statusTransform = parseStatusMap();
        nextFields.job_status.transform = statusTransform ?? (existing?.type === "value_map" ? null : existing);
      }
      const mapping: ImportMappingDocument = {
        version: 1,
        fields: nextFields,
        retain_unmapped: retained.filter((column) => !assignedSources.has(column)),
        skip_rows_where: batch.mapping?.skip_rows_where ?? preview.suggested_mapping?.skip_rows_where ?? [],
      };
      await api.saveImportMapping(organizationId, batch.id, mapping);
      setMessage("Mapping saved. Starting a full-file validation…");
      const validatingBatch = await api.validateImport(organizationId, batch.id);
      onBatchChange(validatingBatch);
    } catch (requestError) {
      setError(requestError instanceof Error && !("status" in requestError) ? requestError.message : getApiErrorMessage(requestError));
      setMessage("The mapping was not saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Fact label="Detected encoding" value={preview.encoding} />
        <Fact label="Detected delimiter" value={preview.delimiter === "\t" ? "Tab" : preview.delimiter} />
        <Fact label="Header row" value={preview.has_header ? "Detected" : "Not detected"} />
      </div>

      {preview.profile_issues.length > 0 && (
        <div className="border-l-4 border-warning bg-[var(--warning-bg)] p-4 text-text-on-accent">
          <p className="font-semibold">Profile findings</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {preview.profile_issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.message}</li>)}
          </ul>
        </div>
      )}

      <Card className="overflow-hidden">
        <div className="border-b border-border-subtle p-5">
          <h2 className="text-xl font-semibold text-text-primary">Map source columns</h2>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            Each source column can feed one destination. Required: service date and either customer name or customer external ID.
          </p>
        </div>
        <div className="divide-y divide-border-subtle">
          {FIELD_GROUPS.map((group) => (
            <section key={group.label} aria-labelledby={`mapping-${group.label.replaceAll(" ", "-")}`} className="p-5">
              <h3 id={`mapping-${group.label.replaceAll(" ", "-")}`} className="text-sm font-semibold uppercase tracking-[0.12em] text-text-secondary">
                {group.label}
              </h3>
              {group.label === "Equipment" && <ImpactHint>Equipment IDs or serials make same-equipment evidence available. Equipment is never invented when identity is missing.</ImpactHint>}
              {group.label === "Financial & detail" && <ImpactHint>Symptoms, diagnosis, and resolution materially improve recurring-issue detection.</ImpactHint>}
              <div className="mt-4 grid gap-x-6 gap-y-4 md:grid-cols-2">
                {group.fields.map((target) => {
                  const selected = fields[target.key]?.source_column;
                  const suggestion = preview.suggestions.find((item) => item.target_field === target.key && item.source_column === selected);
                  return (
                    <div key={target.key}>
                      <Label htmlFor={`map-${target.key}`}>{target.label}{target.required ? " *" : ""}</Label>
                      <Select value={selected ?? UNMAPPED} onValueChange={(value) => updateField(target.key, value)}>
                        <SelectTrigger id={`map-${target.key}`} className="mt-1.5">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={UNMAPPED}>Not mapped</SelectItem>
                          {preview.columns.map((column) => (
                            <SelectItem
                              key={column.name}
                              value={column.name}
                              disabled={assignedSources.has(column.name) && selected !== column.name}
                            >
                              {column.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="mt-1 min-h-5 text-xs text-text-secondary">
                        {suggestion
                          ? `${suggestion.strategy === "synonym" ? "Exact synonym" : "Fuzzy"} suggestion · ${Math.round(suggestion.confidence * 100)}% confidence`
                          : selected ? `Source type: ${preview.columns.find((column) => column.name === selected)?.inferred_type ?? "unknown"}` : "Optional unless marked required"}
                      </p>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </Card>

      {fields.job_status && (
        <Card className="p-5">
          <Label htmlFor="job-status-map">Job status value map</Label>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            Optional. Enter one source=destination pair per line. Supported destinations: completed, cancelled, scheduled, in_progress, unknown.
          </p>
          <Textarea
            id="job-status-map"
            value={statusMap}
            onChange={(event) => setStatusMap(event.target.value)}
            placeholder={"Complete=completed\nClosed=completed\nCanceled=cancelled"}
            className="mt-3 min-h-28 font-mono text-sm"
          />
        </Card>
      )}

      <Card className="p-5">
        <h2 className="text-lg font-semibold text-text-primary">Unmapped source columns</h2>
        <p className="mt-1 text-sm leading-6 text-text-secondary">
          Choose “Keep anyway” to retain a source column in each job&apos;s extra fields. Unchecked columns are not imported.
        </p>
        {unmappedColumns.length ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {unmappedColumns.map((column) => (
              <label key={column.name} className="flex min-h-10 items-center gap-3 rounded-[var(--radius-control)] border border-border-subtle px-3 py-2 text-sm">
                <Checkbox
                  checked={retained.includes(column.name)}
                  onCheckedChange={(checked) => setRetained((current) => checked ? [...new Set([...current, column.name])] : current.filter((item) => item !== column.name))}
                />
                <span className="min-w-0"><span className="block truncate font-medium text-text-primary">{column.name}</span><span className="text-xs text-text-secondary">Keep anyway</span></span>
              </label>
            ))}
          </div>
        ) : <p className="mt-4 text-sm text-text-secondary">Every source column is mapped.</p>}
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-border-subtle p-5">
          <h2 className="text-lg font-semibold text-text-primary">Source preview</h2>
          <p className="mt-1 text-sm text-text-secondary">First five source rows with your destination labels. Values shown here are not normalized output.</p>
        </div>
        <Table className="min-w-max" scrollLabel="Source preview columns">
          <TableHeader>
            <TableRow>
              {preview.columns.map((column) => {
                const target = sourceToTarget[column.name];
                return (
                  <TableHead key={column.name} className="min-w-40 normal-case tracking-normal">
                    <span className="block text-xs font-semibold text-text-primary">{target ? TARGET_LABELS[target] : column.name}</span>
                    {target && <span className="block font-normal text-text-secondary">from {column.name}</span>}
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {preview.sample_rows.slice(0, 5).map((row, rowIndex) => (
              <TableRow key={rowIndex}>
                {preview.columns.map((column) => <TableCell key={column.name} className="max-w-72 truncate">{row[column.name] || "—"}</TableCell>)}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <div className="relative flex flex-col gap-3 border-t border-border-strong bg-surface-canvas py-4 sm:sticky sm:bottom-0 sm:z-20 sm:flex-row sm:items-center sm:justify-between">
        <div aria-live="polite">
          <p className="text-sm text-text-secondary">{message}</p>
          {validationMessages.map((item) => <p key={item} className="mt-1 text-sm font-medium text-danger">{item}</p>)}
          {error && <p className="mt-1 text-sm font-medium text-danger" role="alert">{error}</p>}
        </div>
        <Button onClick={() => void saveAndValidate()} disabled={saving || validationMessages.length > 0}>
          {saving ? "Saving…" : "Save mapping and validate"}
        </Button>
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="border-l-2 border-border-strong pl-3"><p className="text-xs text-text-secondary">{label}</p><p className="mt-1 font-medium text-text-primary">{value || "—"}</p></div>;
}

function ImpactHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-2 max-w-3xl text-sm leading-6 text-brand-deep">{children}</p>;
}
