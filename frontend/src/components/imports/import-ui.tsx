import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { ImportBatch, ImportStatus } from "@/lib/api";

const STATUS_LABELS: Record<ImportStatus, string> = {
  awaiting_file: "Awaiting file",
  uploaded: "Upload received",
  profiling: "Profiling",
  awaiting_mapping: "Mapping needed",
  validating: "Validating",
  validated: "Ready to import",
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  completed_with_errors: "Completed with issues",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STATUS_VARIANTS: Record<ImportStatus, NonNullable<BadgeProps["variant"]>> = {
  awaiting_file: "neutral",
  uploaded: "neutral",
  profiling: "strong",
  awaiting_mapping: "warning",
  validating: "strong",
  validated: "success",
  queued: "strong",
  processing: "strong",
  completed: "success",
  completed_with_errors: "warning",
  failed: "danger",
  cancelled: "neutral",
};

export function ImportStatusBadge({ status }: { status: ImportStatus }) {
  return <Badge variant={STATUS_VARIANTS[status]}>{STATUS_LABELS[status]}</Badge>;
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function formatDateTime(value: string | null, timezone: string): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

export function importedRowCount(batch: ImportBatch): number {
  return Math.max(0, batch.total_rows - batch.error_rows - batch.skipped_rows);
}

export function StepRail({
  active,
  terminal,
}: {
  active: 1 | 2 | 3 | 4;
  terminal?: "complete" | "ended";
}) {
  const steps = ["Upload", "Map columns", "Review issues", "Confirm"];
  return (
    <ol className="grid border-y border-border-subtle sm:grid-cols-4" aria-label="Import progress">
      {steps.map((label, index) => {
        const step = (index + 1) as 1 | 2 | 3 | 4;
        const isCurrent = !terminal && step === active;
        const state = terminal
          ? step < 4 ? "Complete" : terminal === "complete" ? "Complete" : "Ended"
          : step < active ? "Complete" : isCurrent ? "Current" : "Upcoming";
        return (
          <li
            key={label}
            className="flex min-w-0 items-center gap-3 border-b border-border-subtle px-3 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
            aria-current={isCurrent ? "step" : undefined}
          >
            <span className={isCurrent || terminal ? "text-sm font-semibold text-brand-primary" : "text-sm font-semibold text-text-secondary"}>
              {String(step).padStart(2, "0")}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-text-primary">{label}</span>
              <span className="block text-xs text-text-secondary">{state}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ImportPageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-border-subtle pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[30px] font-bold leading-tight text-text-primary sm:text-[36px]">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">{description}</p>
      </div>
      {action}
    </header>
  );
}
