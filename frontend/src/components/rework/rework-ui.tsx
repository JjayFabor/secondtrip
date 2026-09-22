import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Minus,
} from "lucide-react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type {
  CandidateDetail,
  CandidateSignal,
  ReviewDecision,
  ReworkReview,
  ScoreBand,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const DECISION_LABELS: Record<ReviewDecision, string> = {
  confirmed: "Confirmed callback",
  rejected: "Not a callback",
  uncertain: "Uncertain",
};

const DECISION_VARIANTS: Record<ReviewDecision, NonNullable<BadgeProps["variant"]>> = {
  confirmed: "success",
  rejected: "neutral",
  uncertain: "warning",
};

const WORKFLOW_LABELS: Record<CandidateDetail["workflow_status"], string> = {
  open: "Awaiting review",
  in_review: "In review",
  reviewed: "Reviewed",
  dismissed: "Dismissed",
};

export function ScoreBadge({ score, band }: { score: string; band: ScoreBand }) {
  const variant: NonNullable<BadgeProps["variant"]> =
    band === "high" ? "strong" : band === "medium" ? "warning" : "neutral";
  return (
    <Badge variant={variant} className="tabular-nums whitespace-nowrap">
      {formatScore(score)} score · {band}
    </Badge>
  );
}

export function ReviewStatusBadge({
  review,
  workflowStatus,
}: {
  review: ReworkReview | null;
  workflowStatus: CandidateDetail["workflow_status"];
}) {
  if (review) {
    return (
      <Badge variant={DECISION_VARIANTS[review.decision]} className="whitespace-nowrap">
        {DECISION_LABELS[review.decision]}
      </Badge>
    );
  }
  return <Badge variant="neutral" className="whitespace-nowrap">{WORKFLOW_LABELS[workflowStatus]}</Badge>;
}

export function ReviewOutcomeBadge({ decision }: { decision: ReviewDecision }) {
  return <Badge variant={DECISION_VARIANTS[decision]}>{DECISION_LABELS[decision]}</Badge>;
}

export function customerLabel(candidate: Pick<CandidateDetail, "customer">): string {
  return candidate.customer?.display_name || candidate.customer?.account_number || "Customer not provided";
}

export function equipmentLabel(candidate: Pick<CandidateDetail, "equipment">): string {
  const equipment = candidate.equipment;
  if (!equipment) return "Equipment not provided";
  const identity = [equipment.manufacturer, equipment.model].filter(Boolean).join(" ");
  return identity || equipment.equipment_type || equipment.asset_tag || equipment.serial_number || "Equipment not provided";
}

export function formatServiceDate(value: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeZone: timezone,
  }).format(new Date(`${value}T12:00:00Z`));
}

export function formatReviewDate(value: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

export function formatScore(value: string): string {
  const score = Number(value);
  return Number.isFinite(score)
    ? score.toLocaleString(undefined, { maximumFractionDigits: 1 })
    : value;
}

function formatMoney(value: string | null, currencyCode: string): string {
  if (value === null) return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currencyCode,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function VisitComparison({
  candidate,
  timezone,
}: {
  candidate: CandidateDetail;
  timezone: string;
}) {
  return (
    <Card>
      <CardHeader className="border-b border-border-subtle p-5">
        <CardTitle>Visit pair</CardTitle>
        <p className="text-sm text-text-secondary">
          Compare both records as evidence. Neither visit is treated as the conclusion.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid md:grid-cols-[minmax(0,1fr)_48px_minmax(0,1fr)]">
          <VisitRecord
            label="Original visit"
            job={candidate.prior_job}
            timezone={timezone}
          />
          <div className="flex items-center justify-center border-y border-border-subtle py-3 md:border-x md:border-y-0 md:py-0">
            <ArrowRight
              size={18}
              strokeWidth={1.75}
              className="rotate-90 text-brand-primary md:rotate-0"
              aria-label="followed by"
            />
          </div>
          <VisitRecord
            label="Return visit"
            job={candidate.followup_job}
            timezone={timezone}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function VisitRecord({
  label,
  job,
  timezone,
}: {
  label: string;
  job: CandidateDetail["prior_job"];
  timezone: string;
}) {
  const title = job.summary || job.description || "No visit summary provided";
  const detail = job.description && job.description !== title
    ? job.description
    : job.resolution_text || job.diagnosis_text;
  return (
    <section className="min-w-0 p-5" aria-label={label}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-primary">{label}</p>
          <p className="mt-1 text-base font-semibold text-text-primary">
            {formatServiceDate(job.service_date, timezone)}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {job.is_warranty && <Badge variant="warning">Warranty</Badge>}
          {job.is_no_charge && <Badge variant="neutral">No charge</Badge>}
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 text-sm">
        <VisitFact label="Technician" value={job.technician_name || "Not provided"} />
        <VisitFact label="Job number" value={job.job_number || job.external_id || "Not provided"} />
        <VisitFact label="Service" value={job.raw_service_category || "Not provided"} />
        <VisitFact label="Job type" value={job.raw_job_type || "Not provided"} />
        <VisitFact label="Invoice" value={job.invoice_number || "Not provided"} />
        <VisitFact label="Revenue" value={formatMoney(job.revenue_amount, job.currency_code)} numeric />
      </dl>

      <Separator className="my-5" />
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Visit notes</p>
        <p className="mt-2 text-sm font-medium leading-6 text-text-primary">{title}</p>
        {detail && <p className="mt-2 text-sm leading-6 text-text-secondary">{detail}</p>}
      </div>
    </section>
  );
}

function VisitFact({ label, value, numeric }: { label: string; value: string; numeric?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-secondary">{label}</dt>
      <dd className={cn("mt-0.5 break-words font-medium text-text-primary", numeric && "tabular-nums")}>
        {value}
      </dd>
    </div>
  );
}

export function SignalEvidenceList({ signals }: { signals: CandidateSignal[] }) {
  return (
    <Card>
      <CardHeader className="border-b border-border-subtle p-5">
        <CardTitle>Why SecondTrip flagged it</CardTitle>
        <p className="text-sm text-text-secondary">
          Every rule is shown, including evidence that did not match or could not be evaluated.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <ul className="divide-y divide-border-subtle">
          {signals.map((signal) => <SignalRow key={signal.key} signal={signal} />)}
        </ul>
      </CardContent>
    </Card>
  );
}

function SignalRow({ signal }: { signal: CandidateSignal }) {
  const state = {
    matched: {
      label: "Matched",
      icon: CheckCircle2,
      className: "text-brand-primary",
    },
    not_matched: {
      label: "Did not match",
      icon: Circle,
      className: "text-text-secondary",
    },
    not_evaluable: {
      label: "Not evaluable",
      icon: Minus,
      className: "text-text-secondary",
    },
  }[signal.outcome];
  const Icon = state.icon;
  const rawValue = formatRawValue(signal.raw_value);

  return (
    <li className="grid gap-3 px-5 py-4 sm:grid-cols-[148px_minmax(0,1fr)_80px] sm:items-start">
      <div className={cn("flex items-center gap-2 text-xs font-semibold", state.className)}>
        <Icon size={16} strokeWidth={1.9} aria-hidden="true" />
        <span>{state.label}</span>
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-text-primary">{signal.label}</p>
        <p className="mt-1 text-sm leading-6 text-text-secondary">{signal.explanation}</p>
        {rawValue && (
          <p className="mt-1 break-words text-xs text-text-secondary">Observed: {rawValue}</p>
        )}
      </div>
      <div className="text-left sm:text-right">
        <p className="tabular-nums text-sm font-semibold text-text-primary">
          {formatContribution(signal.contribution)}
        </p>
        <p className="text-xs text-text-secondary">contribution</p>
      </div>
    </li>
  );
}

function formatContribution(value: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  const formatted = amount.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return amount > 0 ? `+${formatted}` : formatted;
}

function formatRawValue(value: CandidateSignal["raw_value"]): string | null {
  if (!value || !Object.keys(value).length) return null;
  const entries = Object.entries(value).slice(0, 3);
  return entries
    .map(([key, item]) => `${key.replaceAll("_", " ")}: ${formatRawItem(item)}`)
    .join(" · ");
}

function formatRawItem(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.map(formatRawItem).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export { DECISION_LABELS };
