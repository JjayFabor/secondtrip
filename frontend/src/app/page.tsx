import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check, ClipboardCheck, ShieldCheck, Signal } from "lucide-react";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import { ProductWalkthrough } from "@/components/marketing/product-walkthrough/product-walkthrough";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "SecondTrip — calmer callback operations",
  description: "Help service teams understand callbacks, review patterns, and prevent repeat work.",
};

export default function Home() {
  return (
    <MarketingLayout>
      <section className="border-b border-border-subtle bg-surface-raised">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-16 sm:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-16 lg:py-24">
          <div>
            <Badge variant="neutral">Callback intelligence for service teams</Badge>
            <h1 className="mt-6 max-w-2xl text-[42px] font-bold leading-[1.06] tracking-[-0.035em] text-text-primary sm:text-[56px]">
              Make the second trip easier to prevent.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-text-secondary sm:text-lg">
              SecondTrip gives operations leaders a clear rhythm for spotting repeat work,
              reviewing the signal with their team, and turning the lesson into a better first visit.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link href="/register">
                  Create a free workspace
                  <ArrowRight size={17} aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link href="/login">Sign in</Link>
              </Button>
            </div>
            <div className="mt-9 grid gap-4 border-t border-border-subtle pt-6 sm:grid-cols-3">
              <ProofPoint icon={Signal} label="One shared signal" />
              <ProofPoint icon={ClipboardCheck} label="Human review" />
              <ProofPoint icon={ShieldCheck} label="A record teams can act on" />
            </div>
          </div>

          <ProductPreview />
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
            A useful operating rhythm
          </p>
          <h2 className="mt-3 text-[30px] font-bold leading-tight text-text-primary sm:text-[36px]">
            From a noisy callback list to a calmer conversation.
          </h2>
          <p className="mt-4 text-base leading-7 text-text-secondary">
            Keep the work close to the people who know the job. SecondTrip makes the next best
            question visible without pretending the dashboard knows more than your team does.
          </p>
        </div>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <ProcessCard number="01" title="Signal" description="Bring repeat visits and callback patterns into one place." />
          <ProcessCard number="02" title="Review" description="Give a manager and technician a focused moment to add context." />
          <ProcessCard number="03" title="Prevent" description="Capture the lesson so the next visit starts with better information." />
        </div>
      </section>

      <section
        id="product-preview"
        aria-labelledby="product-preview-heading"
        className="border-t border-border-subtle bg-surface-canvas"
      >
        <div className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
          <div className="grid gap-8 lg:grid-cols-[1.12fr_0.88fr] lg:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
                Product preview
              </p>
              <h2
                id="product-preview-heading"
                className="mt-3 max-w-2xl text-[30px] font-bold leading-tight text-text-primary sm:text-[36px]"
              >
                See how SecondTrip works
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-text-secondary">
                Follow a service-job example from imported history to a reviewed callback and
                estimated rework cost.
              </p>
            </div>
            <div className="border-l-2 border-brand-primary pl-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
                The workflow
              </p>
              <ol className="mt-3 flex flex-wrap gap-x-2 gap-y-2 text-sm font-medium text-text-primary">
                {["Import history", "Find possible returns", "Review evidence", "Classify", "Understand impact"].map(
                  (step, index) => (
                    <li key={step} className="flex items-center gap-2">
                      {index > 0 && (
                        <ArrowRight className="text-brand-primary" size={14} aria-hidden="true" />
                      )}
                      <span>{step}</span>
                    </li>
                  ),
                )}
              </ol>
              <Button asChild variant="secondary" className="mt-5">
                <Link href="/register">Create an account</Link>
              </Button>
            </div>
          </div>

          <div className="mt-10">
            <ProductWalkthrough />
          </div>

          <details className="mt-5 border-t border-border-subtle pt-4 text-sm text-text-secondary">
            <summary className="cursor-pointer font-semibold text-text-primary">
              Text summary of the product preview
            </summary>
            <p className="mt-3 max-w-4xl leading-6">
              A fictional HVAC service-history CSV is previewed locally. SecondTrip surfaces two
              jobs at the same location and equipment, six days apart, for a manager to review.
              The manager confirms the pair as a callback. The preview then estimates $424 of
              rework impact from labor, dispatch, overhead, opportunity cost, and parts.
            </p>
          </details>
        </div>
      </section>

      <section id="faq" className="border-t border-border-subtle bg-surface-inverse text-text-inverse">
        <div className="mx-auto flex max-w-6xl flex-col gap-5 px-6 py-12 sm:flex-row sm:items-center sm:justify-between sm:py-16">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Start small</p>
            <h2 className="mt-2 text-[26px] font-semibold leading-tight sm:text-[30px]">
              See the operating rhythm with a demo workspace.
            </h2>
          </div>
          <Button asChild variant="secondary">
            <Link href="/register">Create an account</Link>
          </Button>
        </div>
      </section>
    </MarketingLayout>
  );
}

function ProofPoint({
  icon: Icon,
  label,
}: {
  icon: typeof Signal;
  label: string;
}) {
  return (
    <div className="flex items-start gap-2 text-sm font-medium text-text-primary">
      <Check className="mt-0.5 shrink-0 text-brand-primary" size={16} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function ProductPreview() {
  return (
    <Card className="overflow-hidden border-border-strong bg-surface-canvas">
      <div className="flex items-center justify-between border-b border-border-subtle bg-surface-raised px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Overview</p>
          <p className="mt-0.5 text-sm font-semibold text-text-primary">Demo workspace</p>
        </div>
        <Badge variant="neutral">No live data</Badge>
      </div>
      <div className="space-y-4 p-4 sm:p-5">
        <div className="grid grid-cols-3 gap-2">
          <PreviewMetric label="Signals" value="—" />
          <PreviewMetric label="In review" value="—" />
          <PreviewMetric label="Prevented" value="—" />
        </div>
        <div className="rounded-[var(--radius-card)] border border-border-subtle bg-surface-raised p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-text-primary">The operating rhythm</p>
              <p className="mt-1 text-xs text-text-secondary">A simple path from signal to action</p>
            </div>
            <span className="text-xs font-medium text-text-secondary">Preview</span>
          </div>
          <div className="mt-5 grid grid-cols-3 gap-2">
            <PreviewStep label="Signal" tone="bg-brand-deep" />
            <PreviewStep label="Review" tone="bg-brand-primary" />
            <PreviewStep label="Prevent" tone="bg-accent" />
          </div>
          <div className="mt-3 h-1 rounded-full bg-border-subtle">
            <div className="h-1 w-2/3 rounded-full bg-brand-primary" />
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-[var(--radius-card)] border border-border-subtle bg-surface-raised px-4 py-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)] bg-[var(--warning-bg)] text-text-on-accent">
            <Signal size={16} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-text-primary">Connect your first source</p>
            <p className="text-xs text-text-secondary">Your next useful signal starts here.</p>
          </div>
          <ArrowRight className="ml-auto shrink-0 text-text-secondary" size={16} aria-hidden="true" />
        </div>
      </div>
    </Card>
  );
}

function PreviewMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-control)] border border-border-subtle bg-surface-raised px-3 py-3">
      <p className="text-[11px] font-medium text-text-secondary">{label}</p>
      <p className="mt-2 text-xl font-semibold text-text-primary">{value}</p>
    </div>
  );
}

function PreviewStep({ label, tone }: { label: string; tone: string }) {
  return (
    <div className="flex items-center gap-2 text-xs font-medium text-text-primary">
      <span className={`h-2.5 w-2.5 rounded-full ${tone}`} aria-hidden="true" />
      {label}
    </div>
  );
}

function ProcessCard({ number, title, description }: { number: string; title: string; description: string }) {
  return (
    <Card className="p-5">
      <p className="text-xs font-semibold tracking-[0.14em] text-brand-primary">{number}</p>
      <h3 className="mt-8 text-xl font-semibold text-text-primary">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-text-secondary">{description}</p>
    </Card>
  );
}
