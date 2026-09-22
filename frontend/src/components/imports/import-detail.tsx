"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { useAppShell } from "@/components/dashboard/app-shell";
import { ImportColumnMapper } from "@/components/imports/import-column-mapper";
import { ImportIssueTable } from "@/components/imports/import-issue-table";
import {
  formatBytes,
  formatDateTime,
  importedRowCount,
  ImportPageHeader,
  ImportStatusBadge,
  StepRail,
} from "@/components/imports/import-ui";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  getApiErrorMessage,
  type ImportBatch,
  type ImportIssues,
  type ImportPreview,
  type ImportStatus,
} from "@/lib/api";

const POLLING_STATUSES = new Set<ImportStatus>([
  "awaiting_file",
  "uploaded",
  "profiling",
  "validating",
  "queued",
  "processing",
]);

const FINAL_STATUSES = new Set<ImportStatus>([
  "completed",
  "completed_with_errors",
  "failed",
  "cancelled",
]);

export function ImportDetailView({
  batchId,
  initialOrganizationId,
  initialBatch,
  initialPreview,
  initialIssues,
  initialError,
  initialActionError,
  initialIssuesError,
}: {
  batchId: string;
  initialOrganizationId?: string;
  initialBatch?: ImportBatch;
  initialPreview?: ImportPreview;
  initialIssues?: ImportIssues;
  initialError?: string;
  initialActionError?: string;
  initialIssuesError?: string;
}) {
  const { organization, canManageImports } = useAppShell();
  const [batch, setBatch] = useState<ImportBatch | undefined>(initialBatch);
  const [preview, setPreview] = useState<ImportPreview | undefined>(initialPreview);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>(initialError);
  const [actionError, setActionError] = useState<string | undefined>(initialActionError);
  const [acting, setActing] = useState(false);
  const [reloadRequest, setReloadRequest] = useState(0);

  const loadBatch = useCallback(async (quiet = false) => {
    if (!organization) {
      return;
    }
    try {
      const nextBatch = await api.getImport(organization.id, batchId);
      setBatch(nextBatch);
      setError(undefined);
    } catch (requestError) {
      if (!quiet) setError(getApiErrorMessage(requestError));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [batchId, organization]);

  useEffect(() => {
    if (!organization) return;
    if (
      organization.id === initialOrganizationId &&
      reloadRequest === 0 &&
      (initialBatch !== undefined || initialError !== undefined)
    ) {
      return;
    }
    let active = true;
    api.getImport(organization.id, batchId)
      .then((nextBatch) => {
        if (!active) return;
        setBatch(nextBatch);
        setError(undefined);
      })
      .catch((requestError: unknown) => {
        if (active) setError(getApiErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [batchId, initialBatch, initialError, initialOrganizationId, organization, reloadRequest]);

  useEffect(() => {
    if (!batch || !POLLING_STATUSES.has(batch.status)) return;
    const interval = window.setInterval(() => void loadBatch(true), 2000);
    return () => window.clearInterval(interval);
  }, [batch, loadBatch]);

  useEffect(() => {
    if (
      !organization ||
      !batch ||
      batch.status !== "awaiting_mapping" ||
      !canManageImports ||
      preview
    ) return;
    let active = true;
    api.getImportPreview(organization.id, batch.id)
      .then((result) => {
        if (!active) return;
        setPreview(result);
        setActionError(undefined);
      })
      .catch((requestError: unknown) => { if (active) setActionError(getApiErrorMessage(requestError)); });
    return () => { active = false; };
  }, [batch, canManageImports, organization, preview]);

  async function cancelImport() {
    if (!organization || !batch) return;
    setActing(true);
    setActionError(undefined);
    try {
      setBatch(await api.cancelImport(organization.id, batch.id));
    } catch (requestError) {
      setActionError(getApiErrorMessage(requestError));
    } finally {
      setActing(false);
    }
  }

  async function commitImport() {
    if (!organization || !batch) return;
    setActing(true);
    setActionError(undefined);
    try {
      const storageKey = `secondtrip:import-commit:${batch.id}`;
      let idempotencyKey = window.localStorage.getItem(storageKey);
      if (!idempotencyKey) {
        idempotencyKey = crypto.randomUUID();
        window.localStorage.setItem(storageKey, idempotencyKey);
      }
      setBatch(await api.commitImport(organization.id, batch.id, idempotencyKey));
    } catch (requestError) {
      setActionError(getApiErrorMessage(requestError));
    } finally {
      setActing(false);
    }
  }

  const historyHref = organization
    ? `/app/imports?org=${encodeURIComponent(organization.id)}`
    : "/app/imports";

  if (loading || (batch && organization && batch.organization_id !== organization.id && !error)) return <ImportDetailLoading />;
  if (error || !batch || !organization) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <Card className="border-danger bg-[var(--danger-bg)] p-6" role="alert">
          <h1 className="text-lg font-semibold text-danger">Could not load this import</h1>
          <p className="mt-2 text-sm text-text-primary">{error ?? "Choose an organization and try again."}</p>
          <Button className="mt-4" variant="secondary" onClick={() => { setLoading(true); setReloadRequest((value) => value + 1); }}>Try again</Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <ImportPageHeader
        title={batch.original_filename ?? "Import detail"}
        description="The status, row counts, and findings below come directly from this import batch."
        action={<Button asChild variant="secondary"><Link href={historyHref}>Back to imports</Link></Button>}
      />
      <StepRail active={activeStep(batch.status)} terminal={terminalRailState(batch.status)} />

      <section aria-labelledby="import-summary-heading" className="grid gap-4 border-b border-border-subtle pb-6 sm:grid-cols-2 lg:grid-cols-5">
        <h2 id="import-summary-heading" className="sr-only">Import summary</h2>
        <SummaryFact label="Status"><ImportStatusBadge status={batch.status} /></SummaryFact>
        <SummaryFact label="Rows" value={batch.total_rows.toLocaleString()} />
        <SummaryFact label="File size" value={formatBytes(batch.file_size_bytes)} />
        <SummaryFact label="Created" value={formatDateTime(batch.created_at, organization.timezone)} />
        <SummaryFact label="Last updated" value={formatDateTime(batch.updated_at, organization.timezone)} />
      </section>

      <div aria-live="polite" className="sr-only">
        Import status is {batch.status}. {batch.processed_rows} of {batch.total_rows} rows processed.
      </div>

      {actionError && <p className="border-l-4 border-danger bg-[var(--danger-bg)] p-4 text-sm font-medium text-danger" role="alert">{actionError}</p>}

      {batch.status === "awaiting_file" && (
        <StatePanel title="Waiting for the source file" description="This batch was created, but storage has not confirmed a CSV upload. Start a new import if the signed upload window expired." />
      )}

      {(batch.status === "uploaded" || batch.status === "profiling") && (
        <ProgressState
          title={batch.status === "uploaded" ? "Upload received" : "Profiling the source file"}
          description={batch.status === "uploaded" ? "The file is queued for source profiling." : "Detecting encoding, delimiter, headers, columns, and sample values before mapping."}
          processed={batch.processed_rows}
          total={batch.total_rows}
          onCancel={canManageImports ? cancelImport : undefined}
          acting={acting}
        />
      )}

      {batch.status === "awaiting_mapping" && (
        canManageImports ? (
          preview ? <ImportColumnMapper organizationId={organization.id} batch={batch} preview={preview} onBatchChange={setBatch} /> : <MappingLoading />
        ) : (
          <StatePanel title="Column mapping needs review" description="An owner, administrator, or manager must confirm how source columns map before validation can start." />
        )
      )}

      {batch.status === "validating" && (
        <ProgressState
          title={`Validating ${batch.total_rows.toLocaleString()} source rows`}
          description="Checking every row without writing jobs. Errors and warnings remain attached to their original row numbers."
          processed={batch.processed_rows}
          total={batch.total_rows}
          onCancel={canManageImports ? cancelImport : undefined}
          acting={acting}
        />
      )}

      {batch.status === "validated" && (
        <ValidatedState
          organizationId={organization.id}
          batch={batch}
          canManage={canManageImports}
          acting={acting}
          onCommit={commitImport}
          initialIssues={initialIssues}
          initialIssuesError={initialIssuesError}
        />
      )}

      {(batch.status === "queued" || batch.status === "processing") && (
        <ProcessingState batch={batch} canManage={canManageImports} acting={acting} onCancel={cancelImport} />
      )}

      {FINAL_STATUSES.has(batch.status) && (
        <FinalState
          organizationId={organization.id}
          timezone={organization.timezone}
          batch={batch}
          initialIssues={initialIssues}
          initialIssuesError={initialIssuesError}
        />
      )}
    </div>
  );
}

function ValidatedState({
  organizationId,
  batch,
  canManage,
  acting,
  onCommit,
  initialIssues,
  initialIssuesError,
}: {
  organizationId: string;
  batch: ImportBatch;
  canManage: boolean;
  acting: boolean;
  onCommit: () => Promise<void>;
  initialIssues?: ImportIssues;
  initialIssuesError?: string;
}) {
  const importing = importedRowCount(batch);
  const notImporting = batch.error_rows + batch.skipped_rows;
  return (
    <div className="space-y-6">
      <CountSummary batch={batch} />
      <ImportIssueTable
        organizationId={organizationId}
        batch={batch}
        initialIssues={initialIssues}
        initialError={initialIssuesError}
      />
      <Card className="border-border-strong p-5 sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">Confirm import</p>
        <h2 className="mt-2 text-xl font-semibold text-text-primary">
          {importing.toLocaleString()} rows will import; {notImporting.toLocaleString()} will not.
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          This writes operational jobs from validated rows. {batch.warning_rows.toLocaleString()} warning rows are included because warnings do not block import.
        </p>
        {canManage ? (
          <div className="mt-5 flex justify-end">
            <Button onClick={() => void onCommit()} disabled={acting}>{acting ? "Starting import…" : "Import validated rows"}</Button>
          </div>
        ) : (
          <p className="mt-4 text-sm font-medium text-text-primary">A manager must confirm this import.</p>
        )}
      </Card>
    </div>
  );
}

function ProcessingState({ batch, canManage, acting, onCancel }: { batch: ImportBatch; canManage: boolean; acting: boolean; onCancel: () => Promise<void> }) {
  return (
    <div className="space-y-6">
      <ProgressState
        title={batch.status === "queued" ? "Import queued" : `Processing ${batch.total_rows.toLocaleString()} validated rows`}
        description={`${batch.created_jobs.toLocaleString()} jobs created · ${batch.updated_jobs.toLocaleString()} jobs updated so far.`}
        processed={batch.processed_rows}
        total={batch.total_rows}
        onCancel={canManage ? onCancel : undefined}
        acting={acting}
      />
      <CountSummary batch={batch} />
    </div>
  );
}

function FinalState({
  organizationId,
  timezone,
  batch,
  initialIssues,
  initialIssuesError,
}: {
  organizationId: string;
  timezone: string;
  batch: ImportBatch;
  initialIssues?: ImportIssues;
  initialIssuesError?: string;
}) {
  const title = batch.status === "completed"
    ? "Import completed"
    : batch.status === "completed_with_errors"
      ? "Import completed with issues"
      : batch.status === "cancelled"
        ? "Import cancelled"
        : "Import failed";
  return (
    <div className="space-y-6">
      <Card className={batch.status === "failed" ? "border-danger p-6" : "border-border-strong p-6"}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-text-primary">{title}</h2>
            <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-text-secondary">{batch.started_at ? "Processing started" : "Batch created"}</dt>
                <dd className="mt-1 tabular-nums font-medium text-text-primary">
                  {formatDateTime(batch.started_at ?? batch.created_at, timezone)}
                </dd>
              </div>
              <div>
                <dt className="text-text-secondary">{batch.completed_at ? "Processing completed" : "Last updated"}</dt>
                <dd className="mt-1 tabular-nums font-medium text-text-primary">
                  {formatDateTime(batch.completed_at ?? batch.updated_at, timezone)}
                </dd>
              </div>
            </dl>
            {batch.failure_reason && <p className="mt-3 text-sm font-medium text-danger">{batch.failure_reason}</p>}
            {batch.status === "cancelled" && batch.processed_rows > 0 && (
              <p className="mt-3 text-sm text-text-primary">Committed work was retained through row {batch.processed_rows.toLocaleString()}.</p>
            )}
          </div>
          <ImportStatusBadge status={batch.status} />
        </div>
      </Card>
      <CountSummary batch={batch} />
      {(batch.error_rows > 0 || batch.warning_rows > 0 || batch.skipped_rows > 0) && (
        <ImportIssueTable
          organizationId={organizationId}
          batch={batch}
          initialIssues={initialIssues}
          initialError={initialIssuesError}
        />
      )}
    </div>
  );
}

function CountSummary({ batch }: { batch: ImportBatch }) {
  const facts = [
    ["Rows", batch.total_rows],
    ["Processed", batch.processed_rows],
    ["Created jobs", batch.created_jobs],
    ["Updated jobs", batch.updated_jobs],
    ["Warning rows", batch.warning_rows],
    ["Error rows", batch.error_rows],
    ["Skipped rows", batch.skipped_rows],
  ] as const;
  return (
    <section aria-labelledby="count-summary-heading">
      <h2 id="count-summary-heading" className="mb-3 text-lg font-semibold text-text-primary">Batch counts</h2>
      <dl className="grid border-y border-border-subtle sm:grid-cols-4 lg:grid-cols-7">
        {facts.map(([label, value]) => (
          <div key={label} className="border-b border-border-subtle px-3 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
            <dt className="text-xs text-text-secondary">{label}</dt>
            <dd className="mt-1 tabular-nums text-xl font-semibold text-text-primary">{value.toLocaleString()}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ProgressState({
  title,
  description,
  processed,
  total,
  onCancel,
  acting,
}: {
  title: string;
  description: string;
  processed: number;
  total: number;
  onCancel?: () => Promise<void>;
  acting: boolean;
}) {
  const progress = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  return (
    <Card className="p-6" aria-live="polite">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-text-primary">{title}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">{description}</p>
          <p className="mt-4 tabular-nums text-sm font-medium text-text-primary">{processed.toLocaleString()} of {total.toLocaleString()} rows · {progress}%</p>
        </div>
        {onCancel && <Button variant="secondary" onClick={() => void onCancel()} disabled={acting}>{acting ? "Cancelling…" : "Cancel"}</Button>}
      </div>
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-border-subtle" role="progressbar" aria-label={title} aria-valuemin={0} aria-valuemax={Math.max(total, 1)} aria-valuenow={processed}>
        <div className="h-full bg-brand-primary transition-[width] duration-[var(--duration-base)]" style={{ width: `${progress}%` }} />
      </div>
    </Card>
  );
}

function StatePanel({ title, description }: { title: string; description: string }) {
  return <Card className="p-6" aria-live="polite"><h2 className="text-xl font-semibold text-text-primary">{title}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">{description}</p></Card>;
}

function SummaryFact({ label, value, children }: { label: string; value?: string; children?: React.ReactNode }) {
  return <div><p className="text-xs text-text-secondary">{label}</p><div className="mt-1 tabular-nums text-sm font-medium text-text-primary">{children ?? value}</div></div>;
}

function ImportDetailLoading() {
  return <div className="mx-auto w-full max-w-7xl space-y-5" aria-label="Loading import"><Skeleton className="h-20" /><Skeleton className="h-16" /><Skeleton className="h-64" /></div>;
}

function MappingLoading() {
  return <div className="space-y-4" aria-label="Loading source preview"><Skeleton className="h-20" /><Skeleton className="h-96" /></div>;
}

function activeStep(status: ImportStatus): 1 | 2 | 3 | 4 {
  if (["awaiting_file", "uploaded", "profiling"].includes(status)) return 1;
  if (status === "awaiting_mapping") return 2;
  if (["validating", "validated"].includes(status)) return 3;
  return 4;
}

function terminalRailState(status: ImportStatus): "complete" | "ended" | undefined {
  if (status === "completed" || status === "completed_with_errors") return "complete";
  if (status === "failed" || status === "cancelled") return "ended";
  return undefined;
}
