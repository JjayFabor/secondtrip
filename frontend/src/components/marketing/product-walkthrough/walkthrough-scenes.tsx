import {
  Check,
  ClipboardCheck,
  FileSpreadsheet,
  FileWarning,
  FolderInput,
  HelpCircle,
  LayoutGrid,
  LineChart,
  LogOut,
  MapPin,
  Menu,
  Search,
  Settings,
  Settings2,
  UserCircle,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import styles from "./walkthrough.module.css";
import {
  COST_LINES,
  DEMO_FILE,
  DEMO_JOBS,
  DEMO_QUEUE,
  ESTIMATED_TOTAL,
  EVIDENCE,
} from "./walkthrough-data";
import type { WalkthroughSceneId } from "./walkthrough-storyboard";

interface SceneProps {
  sceneId: WalkthroughSceneId;
  progress: number;
}

export function WalkthroughWorkspace({ sceneId, progress }: SceneProps) {
  return (
    <div className="grid h-full grid-cols-1 bg-surface-raised lg:grid-cols-[224px_1fr]">
      <AppRail sceneId={sceneId} />
      <div className="flex h-full min-h-0 min-w-0 flex-col">
        <AppHeader sceneId={sceneId} />
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface-canvas p-3 sm:p-5 lg:p-6">
          {sceneId === "import" && <ImportScene progress={progress} />}
          {sceneId === "queue" && <QueueScene progress={progress} />}
          {sceneId === "evidence" && <EvidenceScene progress={progress} />}
          {sceneId === "classify" && <ClassifyScene progress={progress} />}
          {sceneId === "impact" && <ImpactScene progress={progress} />}
        </div>
      </div>
    </div>
  );
}

function AppRail({ sceneId }: { sceneId: WalkthroughSceneId }) {
  const primaryItems = [
    { label: "Overview", icon: LayoutGrid },
    { label: "Visits", icon: Wrench },
    { label: "Callbacks", icon: FileWarning },
    { label: "Patterns", icon: LineChart },
    { label: "Reports", icon: LineChart },
    { label: "Imports", icon: FolderInput },
  ] as const;
  const secondaryItems = [
    { label: "Settings", icon: Settings },
    { label: "Help", icon: HelpCircle },
    { label: "Account", icon: UserCircle },
  ] as const;
  const activeLabel =
    sceneId === "import" ? "Imports" : sceneId === "impact" ? "Reports" : "Callbacks";

  return (
    <aside className="hidden h-full border-r border-border-subtle bg-surface-raised p-3 lg:flex lg:flex-col">
      <div className="flex h-10 items-center px-2">
        <Logo variant="horizontal" />
      </div>
      <nav aria-label="Preview workspace" className="mt-2 flex min-h-0 flex-1 flex-col">
        <ul className="flex flex-col gap-0.5">
          {primaryItems.map((item) => (
            <PreviewNavItem key={item.label} item={item} active={item.label === activeLabel} />
          ))}
        </ul>
        <div className="my-2 mt-auto h-px bg-border-subtle" />
        <ul className="flex flex-col gap-0.5">
          {secondaryItems.map((item) => (
            <PreviewNavItem key={item.label} item={item} active={false} />
          ))}
        </ul>
      </nav>
    </aside>
  );
}

function PreviewNavItem({
  item,
  active,
}: {
  item: { label: string; icon: LucideIcon };
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <li>
      <div
        className={cn(
          "flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-2 text-sm font-medium",
          active ? "bg-surface-canvas text-text-primary" : "text-text-secondary",
        )}
        aria-current={active ? "page" : undefined}
      >
        <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
        {item.label}
      </div>
    </li>
  );
}

function AppHeader({ sceneId }: { sceneId: WalkthroughSceneId }) {
  const label = {
    import: "Imports",
    queue: "Review queue",
    evidence: "Candidate evidence",
    classify: "Candidate review",
    impact: "Rework impact",
  }[sceneId];

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border-subtle bg-surface-raised px-4">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-text-secondary lg:hidden">
        <Menu size={20} strokeWidth={1.75} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-text-primary">Northstar Mechanical</p>
        <p className="truncate text-[11px] text-text-secondary">Manager · Sample workspace</p>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <div className="hidden text-right sm:block">
          <p className="max-w-32 truncate text-xs font-medium text-text-primary">M. Reyes</p>
          <p className="max-w-32 truncate text-[11px] text-text-secondary">{label}</p>
        </div>
        <span className="flex h-8 items-center gap-1.5 rounded-[var(--radius-control)] px-2 text-[11px] font-semibold text-text-primary">
          <LogOut size={15} aria-hidden="true" />
          <span className="hidden sm:inline">Sign out</span>
        </span>
      </div>
    </header>
  );
}

function ImportScene({ progress }: { progress: number }) {
  const selected = progress >= 0.24;
  const processed = progress >= 0.64;

  return (
    <div className="mx-auto max-w-3xl">
      <SceneHeading eyebrow="Import history" title="Map the records you already use" />
      <div className="mt-4 grid gap-3 md:grid-cols-[0.78fr_1.22fr]">
        <div className="border border-border-strong bg-surface-raised p-4">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-[var(--warning-bg)] text-text-on-accent">
              <FileSpreadsheet size={18} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-text-primary">{DEMO_FILE.name}</p>
              <p className="mt-1 text-xs text-text-secondary">CSV · {DEMO_FILE.rows} sample records</p>
            </div>
          </div>
          <div className="mt-5 border-t border-border-subtle pt-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              Local preview
            </p>
            <div className="mt-3 flex items-center gap-2 text-xs font-medium text-text-primary">
              <span
                className={cn(
                  "flex h-5 w-5 items-center justify-center rounded-full border",
                  selected
                    ? "border-brand-primary bg-brand-primary text-text-inverse"
                    : "border-border-strong bg-surface-raised text-transparent",
                )}
              >
                <Check size={12} aria-hidden="true" />
              </span>
              {selected ? "File selected" : "Ready to select"}
            </div>
          </div>
          <div
            className={cn(
              "mt-4 border-l-2 px-3 py-2 text-xs",
              processed
                ? "border-brand-primary bg-[color-mix(in_srgb,var(--color-brand-primary)_8%,white)] text-text-primary"
                : "border-border-subtle bg-surface-canvas text-text-secondary",
              processed && styles.reveal,
            )}
          >
            {processed ? "248 records ready for review" : "Previewing supported fields"}
          </div>
        </div>

        <div className="min-w-0 overflow-hidden border border-border-strong bg-surface-raised">
          <div className="border-b border-border-subtle px-4 py-3">
            <p className="text-xs font-semibold text-text-primary">Supported field preview</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[460px] text-left text-[11px]">
              <thead className="border-b border-border-subtle bg-surface-canvas text-text-secondary">
                <tr>
                  <th className="px-3 py-2 font-medium">job_id</th>
                  <th className="px-3 py-2 font-medium">service_date</th>
                  <th className="px-3 py-2 font-medium">location</th>
                  <th className="px-3 py-2 font-medium">equipment</th>
                </tr>
              </thead>
              <tbody className="text-text-primary">
                <PreviewRow values={["ST-1048", "2026-06-12", "14 Cedar Lane", "RTU-2"]} />
                <PreviewRow values={["ST-1071", "2026-06-18", "14 Cedar Lane", "RTU-2"]} />
                <PreviewRow values={["ST-1094", "2026-06-20", "8 Harbor Road", "AHU-1"]} />
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-1.5 border-t border-border-subtle px-3 py-3">
            {DEMO_FILE.fields.map((field) => (
              <span
                key={field}
                className="rounded-full border border-border-strong bg-surface-raised px-2 py-0.5 text-[10px] font-medium text-text-secondary"
              >
                {field}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PreviewRow({ values }: { values: readonly string[] }) {
  return (
    <tr className="border-b border-border-subtle last:border-0">
      {values.map((value) => (
        <td key={value} className="whitespace-nowrap px-3 py-2.5">
          {value}
        </td>
      ))}
    </tr>
  );
}

function QueueScene({ progress }: { progress: number }) {
  const highlighted = progress >= 0.34;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-end justify-between gap-4">
        <SceneHeading eyebrow="Review queue" title="Possible return visits" />
        <p className="hidden text-xs text-text-secondary sm:block">3 pairs to review</p>
      </div>
      <div className="mt-4 overflow-hidden border border-border-strong bg-surface-raised">
        <div className="grid grid-cols-[1fr_auto] border-b border-border-subtle bg-surface-canvas px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-text-secondary sm:grid-cols-[1.3fr_1.4fr_0.55fr_0.8fr]">
          <span>Account</span>
          <span className="hidden sm:block">Issue / equipment</span>
          <span className="hidden sm:block">Interval</span>
          <span>Status</span>
        </div>
        {DEMO_QUEUE.map((item, index) => {
          const isActive = item.highlighted && highlighted;
          return (
            <div
              key={item.id}
              className={cn(
                "grid grid-cols-[1fr_auto] items-center gap-3 border-b border-border-subtle px-3 py-3 last:border-0 sm:grid-cols-[1.3fr_1.4fr_0.55fr_0.8fr]",
                isActive && "border-l-[3px] border-l-brand-primary bg-[color-mix(in_srgb,var(--color-brand-primary)_7%,white)]",
                progress > index * 0.12 && styles.rowReveal,
              )}
            >
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-text-primary">{item.account}</p>
                <p className="mt-0.5 text-[10px] text-text-secondary">{item.id}</p>
              </div>
              <p className="hidden truncate text-xs text-text-primary sm:block">{item.issue}</p>
              <p className="hidden text-xs font-medium text-text-primary sm:block">{item.interval}</p>
              {isActive ? (
                <Badge variant="strong" className="justify-self-end sm:justify-self-start">
                  Possible callback
                </Badge>
              ) : (
                <Badge variant="neutral" className="justify-self-end sm:justify-self-start">
                  {item.status}
                </Badge>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex items-start gap-2 text-xs leading-5 text-text-secondary">
        <Search className="mt-0.5 shrink-0 text-brand-primary" size={14} aria-hidden="true" />
        <p>
          The highlighted pair shares a site and equipment and occurred 6 days apart. The signal
          surfaces it for human review; it does not decide the outcome.
        </p>
      </div>
    </div>
  );
}

function EvidenceScene({ progress }: { progress: number }) {
  const revealSignals = Math.min(EVIDENCE.length, Math.max(1, Math.floor(progress * 6)));

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SceneHeading eyebrow="Candidate ST-1048 → ST-1071" title="Why this pair was flagged" />
        <Badge variant="strong">Possible callback</Badge>
      </div>
      <div className="mt-3 hidden gap-3 md:grid md:grid-cols-2">
        <JobRecord label="Original visit" job={DEMO_JOBS.original} />
        <JobRecord label="Return visit · 6 days later" job={DEMO_JOBS.returnVisit} />
      </div>
      <CompactJobComparison />
      <div className="mt-3 border border-border-strong bg-surface-raised">
        <div className="border-b border-border-subtle px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
            Evidence breakdown
          </p>
        </div>
        <div className="grid grid-cols-2">
          {EVIDENCE.map((signal, index) => (
            <div
              key={signal.label}
              className={cn(
                "flex min-h-12 items-center gap-2 border-b border-border-subtle px-2 py-2 [&:nth-child(odd)]:border-r [&:nth-last-child(-n+2)]:border-b-0 sm:px-3",
                index < revealSignals ? "opacity-100" : "opacity-35",
                index < revealSignals && styles.reveal,
              )}
            >
              <Check className="shrink-0 text-success" size={15} aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-text-primary">{signal.label}</p>
                <p className="truncate text-[11px] text-text-secondary">{signal.detail}</p>
              </div>
              <span className="ml-auto tabular-nums text-xs font-semibold text-brand-primary">
                {signal.strength}
              </span>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-2 text-[11px] leading-4 text-text-secondary">
        Notes support the review context. Similarity uses imported problem fields, not technician
        note text.
      </p>
    </div>
  );
}

function CompactJobComparison() {
  return (
    <section className="mt-3 border border-border-strong bg-surface-raised md:hidden">
      <div className="grid grid-cols-2 border-b border-border-subtle bg-surface-canvas">
        <div className="border-r border-border-subtle px-2.5 py-2">
          <p className="text-[11px] font-semibold text-text-primary">Original · Jun 12</p>
          <p className="text-[11px] text-text-secondary">ST-1048</p>
        </div>
        <div className="px-2.5 py-2">
          <p className="text-[11px] font-semibold text-text-primary">Return · Jun 18</p>
          <p className="text-[11px] text-text-secondary">ST-1071 · 6 days later</p>
        </div>
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 border-b border-border-subtle px-2.5 py-2 text-[11px] leading-4">
        <MapPin className="mt-0.5 text-brand-primary" size={12} aria-hidden="true" />
        <span className="text-text-secondary">14 Cedar Lane · same location</span>
        <Wrench className="mt-0.5 text-brand-primary" size={12} aria-hidden="true" />
        <span className="text-text-secondary">RTU-2 · Lennox LGA090 · same equipment</span>
      </div>
      <div className="grid grid-cols-2">
        <div className="border-r border-border-subtle p-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
            Issue
          </p>
          <p className="mt-1 text-[11px] font-medium leading-4 text-text-primary">
            {DEMO_JOBS.original.issue}
          </p>
          <p className="mt-2 text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
            Technician note
          </p>
          <p className="mt-1 text-[11px] leading-4 text-text-secondary">
            {DEMO_JOBS.original.note}
          </p>
        </div>
        <div className="p-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
            Issue
          </p>
          <p className="mt-1 text-[11px] font-medium leading-4 text-text-primary">
            {DEMO_JOBS.returnVisit.issue}
          </p>
          <p className="mt-2 text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
            Technician note
          </p>
          <p className="mt-1 text-[11px] leading-4 text-text-secondary">
            {DEMO_JOBS.returnVisit.note}
          </p>
        </div>
      </div>
    </section>
  );
}

function JobRecord({
  label,
  job,
}: {
  label: string;
  job: (typeof DEMO_JOBS)[keyof typeof DEMO_JOBS];
}) {
  return (
    <article className="border border-border-strong bg-surface-raised">
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">{label}</p>
        <span className="text-[11px] font-semibold text-text-primary">{job.date}</span>
      </div>
      <div className="space-y-2 p-3">
        <p className="text-xs font-semibold text-text-primary">{job.customer}</p>
        <div className="flex gap-2 text-[11px] text-text-secondary">
          <MapPin className="mt-0.5 shrink-0" size={12} aria-hidden="true" />
          <span>{job.location}</span>
        </div>
        <div className="flex gap-2 text-[11px] text-text-secondary">
          <Wrench className="mt-0.5 shrink-0" size={12} aria-hidden="true" />
          <span>{job.equipment}</span>
        </div>
        <p className="border-l-2 border-brand-primary pl-2 text-[11px] font-medium text-text-primary">
          {job.issue}
        </p>
        <p className="bg-surface-canvas px-2 py-1.5 text-[11px] leading-4 text-text-secondary">
          <span className="font-semibold text-text-primary">Technician note: </span>
          {job.note}
        </p>
      </div>
    </article>
  );
}

function ClassifyScene({ progress }: { progress: number }) {
  const confirmed = progress >= 0.48;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SceneHeading eyebrow="Human review" title="Make the final call" />
        <Badge variant={confirmed ? "success" : "neutral"}>
          {confirmed ? "Confirmed" : "Awaiting review"}
        </Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_0.82fr]">
        <div className="border border-border-strong bg-surface-raised p-4">
          <p className="text-xs font-semibold text-text-primary">Cedar Lane Dental · RTU-2</p>
          <p className="mt-1 text-[11px] text-text-secondary">ST-1048 → ST-1071 · 6 days</p>
          <div className="mt-4 space-y-2">
            <DecisionOption
              label="Confirmed"
              description="Confirmed callback"
              active={confirmed}
            />
            <DecisionOption label="Rejected" description="Unrelated" active={false} />
            <DecisionOption label="Unsure" description="Needs more context" active={false} />
          </div>
        </div>
        <div
          className={cn(
            "flex flex-col justify-between border border-border-strong bg-surface-raised p-4",
            confirmed && styles.pulseOnce,
          )}
        >
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              Review record
            </p>
            <p className="mt-3 text-sm font-semibold text-text-primary">
              {confirmed ? "Confirmed callback" : "No decision recorded"}
            </p>
            <p className="mt-2 text-xs leading-5 text-text-secondary">
              {confirmed
                ? "A manager reviewed the evidence and classified this pair. The machine signal remains separate from the human decision."
                : "The evidence is ready for a manager to review."}
            </p>
          </div>
          <div className="mt-6 flex items-center gap-2 border-t border-border-subtle pt-3 text-[11px] text-text-secondary">
            <ClipboardCheck size={14} className="text-brand-primary" aria-hidden="true" />
            {confirmed ? "Decision recorded by M. Reyes" : "Manager decision required"}
          </div>
        </div>
      </div>
    </div>
  );
}

function DecisionOption({
  label,
  description,
  active,
}: {
  label: string;
  description: string;
  active: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-h-12 items-center gap-3 rounded-[var(--radius-control)] border px-3 py-2",
        active
          ? "border-brand-primary bg-[color-mix(in_srgb,var(--color-brand-primary)_8%,white)]"
          : "border-border-subtle bg-surface-canvas",
      )}
    >
      <span
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded-full border",
          active ? "border-brand-primary bg-brand-primary text-text-inverse" : "border-border-strong",
        )}
      >
        {active && <Check size={12} aria-hidden="true" />}
      </span>
      <div>
        <p className="text-xs font-semibold text-text-primary">{label}</p>
        <p className="text-[10px] text-text-secondary">{description}</p>
      </div>
    </div>
  );
}

function ImpactScene({ progress }: { progress: number }) {
  const lineCount = Math.min(COST_LINES.length, Math.max(1, Math.floor(progress * 7)));
  const showTotal = progress >= 0.72;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SceneHeading eyebrow="Confirmed callback" title="Estimated rework impact" />
        <Badge variant="success">Human reviewed</Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-[1.25fr_0.75fr]">
        <div className="overflow-hidden border border-border-strong bg-surface-raised">
          <div className="grid grid-cols-[1fr_auto] border-b border-border-subtle bg-surface-canvas px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-text-secondary sm:grid-cols-[0.8fr_1fr_auto]">
            <span>Cost category</span>
            <span className="hidden sm:block">Checkable input</span>
            <span>Estimated</span>
          </div>
          {COST_LINES.map((line, index) => (
            <div
              key={line.label}
              className={cn(
                "grid grid-cols-[1fr_auto] border-b border-border-subtle px-3 py-2.5 text-xs sm:grid-cols-[0.8fr_1fr_auto]",
                index < lineCount ? "opacity-100" : "opacity-25",
                index < lineCount && styles.rowReveal,
              )}
            >
              <span className="min-w-0 font-medium text-text-primary">
                <span className="block">{line.label}</span>
                <span className="mt-0.5 block text-[11px] font-normal leading-4 text-text-secondary sm:hidden">
                  {line.input}
                </span>
              </span>
              <span className="hidden text-text-secondary sm:block">{line.input}</span>
              <span className="tabular-nums font-semibold text-text-primary">{line.amount}</span>
            </div>
          ))}
          <div className="grid grid-cols-[1fr_auto] bg-[var(--warning-bg)] px-3 py-3 text-sm font-semibold text-text-on-accent">
            <span>Estimated total</span>
            <span className={cn("tabular-nums", showTotal ? "opacity-100" : "opacity-0")}>
              {ESTIMATED_TOTAL}
            </span>
          </div>
        </div>
        <aside className="border border-border-strong bg-surface-raised p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
            Reviewed case
          </p>
          <p className="mt-3 text-sm font-semibold text-text-primary">Cooling / condensate issue</p>
          <p className="mt-1 text-xs text-text-secondary">Cedar Lane Dental · RTU-2</p>
          <div className="mt-5 border-t border-border-subtle pt-4">
            <p className="text-[11px] leading-5 text-text-secondary">
              Labor and opportunity cost use the 2.5-hour return visit. Parts come from return-visit
              line items; the original invoice is not used as cost.
            </p>
          </div>
          <div className="mt-4 flex items-center gap-2 text-[11px] font-medium text-text-primary">
            <Settings2 size={14} className="text-brand-primary" aria-hidden="true" />
            Cost model v1 · USD
          </div>
        </aside>
      </div>
    </div>
  );
}

function SceneHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-primary">
        {eyebrow}
      </p>
      <h4 className="mt-1 text-base font-semibold leading-tight text-text-primary sm:text-lg">
        {title}
      </h4>
    </div>
  );
}
