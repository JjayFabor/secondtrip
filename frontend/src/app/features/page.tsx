import Link from "next/link";
import { ArrowRight, CircleCheck, CircleMinus, FileUp, Scale } from "lucide-react";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import {
  CheckList,
  FinalCta,
  PageHero,
  SectionHeading,
} from "@/components/marketing/page-elements";
import { JsonLd } from "@/components/seo/json-ld";
import { Button } from "@/components/ui/button";
import { breadcrumbJsonLd, pageMetadata, softwareApplicationJsonLd } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Product overview",
  description:
    "See how SecondTrip imports job history, detects possible repeat visits, explains every signal, and records a human decision.",
  path: "/features",
});

const STAGES = [
  {
    number: "01",
    title: "Import",
    description:
      "Upload a CSV, map its columns, preview the normalized records, and resolve validation issues before committing the import.",
  },
  {
    number: "02",
    title: "Detect",
    description:
      "Deterministic rules compare service visits within a configured window and surface pairs that deserve a closer look.",
  },
  {
    number: "03",
    title: "Explain",
    description:
      "See both visits, the score arithmetic, and every signal—including evidence that did not match or could not be evaluated.",
  },
  {
    number: "04",
    title: "Review",
    description:
      "A manager confirms, rejects, or marks the pair uncertain. Reclassifications remain visible in append-only history.",
  },
] as const;

export default function FeaturesPage() {
  return (
    <MarketingLayout>
      <JsonLd
        data={[
          softwareApplicationJsonLd(),
          breadcrumbJsonLd([
            { name: "Home", path: "/" },
            { name: "Product", path: "/features" },
          ]),
        ]}
      />
      <PageHero
        eyebrow="Product"
        title="A clear evidence trail from service history to human decision."
        description="SecondTrip helps operations teams find possible callbacks without replacing the CRM or field-service system that already runs the business."
        aside={<EvidencePreview />}
      />

      <section className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
        <SectionHeading
          eyebrow="The workflow"
          title="Four stages, one accountable review."
          description="The software does the repetitive comparison work. Your team keeps the final say."
        />
        <ol className="mt-10 border-t border-border-strong">
          {STAGES.map((stage) => (
            <li
              key={stage.number}
              className="grid gap-3 border-b border-border-subtle py-7 sm:grid-cols-[5rem_10rem_1fr] sm:items-start"
            >
              <span className="text-sm font-semibold text-brand-primary">{stage.number}</span>
              <h3 className="text-xl font-semibold text-text-primary">{stage.title}</h3>
              <p className="max-w-2xl text-base leading-7 text-text-secondary">
                {stage.description}
              </p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-y border-border-subtle bg-surface-raised">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-16 sm:py-20 lg:grid-cols-2">
          <div>
            <SectionHeading
              eyebrow="Evidence, not a black box"
              title="See why a pair surfaced—and what did not match."
              description="A strong score is a prompt to review, not a verdict. SecondTrip keeps the supporting and contradictory evidence together."
            />
          </div>
          <div className="space-y-6">
            <CheckList
              items={[
                "Both service visits shown side by side",
                "Signal outcome and contribution shown separately",
                "Non-matches and not-evaluable fields kept visible",
                "Score calculation shown rather than hidden",
                "Human classification and prior reviews preserved",
              ]}
            />
            <Button asChild variant="secondary">
              <Link href="/#product-preview">
                Watch the product walkthrough
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
        <div className="grid gap-12 lg:grid-cols-2">
          <SectionHeading
            eyebrow="Fit and limits"
            title="Built for a specific operating question."
            description="SecondTrip is useful when your job history is available as a CSV and a manager can review the surfaced pairs."
          />
          <div className="grid gap-8 sm:grid-cols-2">
            <div>
              <h3 className="font-semibold text-text-primary">A good fit when</h3>
              <CheckList
                items={[
                  "You already record service visits in a CRM or FSM",
                  "Repeat visits are difficult to review consistently",
                  "Your team wants transparent, deterministic evidence",
                ]}
              />
            </div>
            <div>
              <h3 className="font-semibold text-text-primary">Not designed to</h3>
              <ul className="mt-3 space-y-3">
                {["Replace your CRM or FSM", "Make the final classification", "Infer missing import data"].map(
                  (item) => (
                    <li key={item} className="flex gap-3 text-sm leading-6 text-text-secondary">
                      <CircleMinus className="mt-1 shrink-0" size={16} aria-hidden="true" />
                      {item}
                    </li>
                  ),
                )}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <FinalCta />
    </MarketingLayout>
  );
}

function EvidencePreview() {
  return (
    <div className="border border-border-strong bg-surface-canvas">
      <div className="grid grid-cols-2 border-b border-border-subtle">
        <div className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">First visit</p>
          <p className="mt-2 text-sm font-semibold text-text-primary">Repair completed</p>
          <p className="mt-1 text-xs text-text-secondary">12 September</p>
        </div>
        <div className="border-l border-border-subtle p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Return visit</p>
          <p className="mt-2 text-sm font-semibold text-text-primary">Similar issue reported</p>
          <p className="mt-1 text-xs text-text-secondary">18 September</p>
        </div>
      </div>
      <div className="space-y-3 p-4">
        <EvidenceRow icon={CircleCheck} label="Same customer" value="Matched" />
        <EvidenceRow icon={CircleCheck} label="Same equipment" value="Matched" />
        <EvidenceRow icon={Scale} label="Description similarity" value="Not evaluable" muted />
        <div className="flex items-center justify-between border-t border-border-subtle pt-4">
          <span className="text-sm font-semibold text-text-primary">Human decision</span>
          <span className="bg-[var(--warning-bg)] px-3 py-1 text-xs font-semibold text-text-on-accent">
            Awaiting review
          </span>
        </div>
      </div>
    </div>
  );
}

function EvidenceRow({
  icon: Icon,
  label,
  value,
  muted = false,
}: {
  icon: typeof FileUp;
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <Icon className={muted ? "text-text-secondary" : "text-brand-primary"} size={17} aria-hidden="true" />
      <span className="text-text-primary">{label}</span>
      <span className="ml-auto text-text-secondary">{value}</span>
    </div>
  );
}
