import Link from "next/link";
import { ArrowRight, Check, ClipboardCheck, FileUp, Search, ShieldCheck } from "lucide-react";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import { FinalCta, SectionHeading } from "@/components/marketing/page-elements";
import { ProductWalkthrough } from "@/components/marketing/product-walkthrough/product-walkthrough";
import { JsonLd } from "@/components/seo/json-ld";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  faqJsonLd,
  pageMetadata,
  softwareApplicationJsonLd,
  type FaqEntry,
} from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Callback and rework analytics",
  description:
    "Import service-job history, surface possible repeat visits, inspect every signal, and record the human decision without replacing your CRM or FSM.",
  path: "/",
});

const FAQS: readonly FaqEntry[] = [
  {
    question: "Does SecondTrip replace our CRM or field-service system?",
    answer:
      "No. SecondTrip supplements the system you already use. You export job history as a CSV, review possible callbacks in SecondTrip, and keep running daily operations in your existing CRM or FSM.",
  },
  {
    question: "How does SecondTrip decide that two visits may be related?",
    answer:
      "Deterministic rules compare details such as timing, customer, location, and equipment when those fields are available. The product shows the complete signal breakdown and score arithmetic rather than presenting a hidden verdict.",
  },
  {
    question: "Does a high score mean a visit is definitely a callback?",
    answer:
      "No. A score measures the strength of the available evidence. A manager still confirms, rejects, or marks the pair uncertain, and that human decision is kept separately from the score.",
  },
  {
    question: "What happens when a field is missing?",
    answer:
      "SecondTrip does not invent missing import data. A signal can be shown as not evaluable, and import rows missing required identity or date information are reported for correction.",
  },
  {
    question: "What does the private beta cost?",
    answer:
      "The private beta is currently free. Payment processing is not enabled, and current usage boundaries are listed on the pricing page.",
  },
];

export default function Home() {
  return (
    <MarketingLayout>
      <JsonLd data={[softwareApplicationJsonLd(), faqJsonLd(FAQS)]} />
      <section className="border-b border-border-subtle bg-surface-raised">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-16 sm:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-16 lg:py-24">
          <div>
            <Badge variant="neutral">Callback intelligence for service teams</Badge>
            <h1 className="mt-6 max-w-3xl text-4xl font-bold leading-tight tracking-tight text-text-primary sm:text-5xl">
              Turn job history into a clear callback review.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-text-secondary">
              Import service history, surface possible repeat visits, review every piece of
              evidence, and record the human decision—without replacing your existing CRM or FSM.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link href="/register">
                  Create a free workspace
                  <ArrowRight size={17} aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link href="/features">Explore the product</Link>
              </Button>
            </div>
            <div className="mt-9 grid gap-4 border-t border-border-subtle pt-6 sm:grid-cols-3">
              <ProofPoint label="Deterministic signals" />
              <ProofPoint label="Complete evidence" />
              <ProofPoint label="Human review history" />
            </div>
          </div>
          <VisitPairPreview />
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <SectionHeading
            eyebrow="How it works"
            title="From exported history to an accountable decision."
            description="The repetitive comparison is automated. Context and judgment remain with the team that knows the work."
          />
          <Link className="inline-flex items-center gap-2 font-semibold text-brand-primary" href="/features">
            Product details <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        <ol className="mt-10 grid border-y border-border-strong md:grid-cols-4">
          <ProcessStep number="01" icon={FileUp} title="Import" description="Map and validate a CSV export." />
          <ProcessStep number="02" icon={Search} title="Detect" description="Surface possible return visits." />
          <ProcessStep number="03" icon={ShieldCheck} title="Explain" description="Show every signal and score." />
          <ProcessStep number="04" icon={ClipboardCheck} title="Review" description="Record the human classification." />
        </ol>
      </section>

      <section className="border-y border-border-subtle bg-surface-raised">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 sm:py-20 lg:grid-cols-2 lg:items-center">
          <SectionHeading
            eyebrow="Fits the workflow you have"
            title="Add a review layer, not another operating system."
            description="SecondTrip starts with a CSV export from the system where your team already closes jobs. It gives managers a focused place to inspect possible callbacks and preserve the decision trail."
          />
          <div className="border-l-2 border-brand-primary pl-6">
            <ol className="space-y-5 text-sm">
              <WorkflowLine label="Your CRM or FSM" detail="remains the operational source" />
              <WorkflowLine label="SecondTrip" detail="compares history and explains possible pairs" />
              <WorkflowLine label="Your team" detail="makes and records the decision" />
            </ol>
          </div>
        </div>
      </section>

      <section id="product-preview">
        <div className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
          <div className="grid gap-8 lg:grid-cols-[1.12fr_0.88fr] lg:items-end">
            <SectionHeading
              eyebrow="Product walkthrough"
              title="Follow one fictional pair from CSV to review."
              description="The local walkthrough shows the product rhythm using fictional service data. It does not connect to a live workspace."
            />
            <div className="border-l-2 border-brand-primary pl-5">
              <p className="text-sm font-semibold text-text-primary">Import → detect → explain → review</p>
              <p className="mt-2 text-sm leading-6 text-text-secondary">
                Pause, replay, or move through the scenes manually.
              </p>
            </div>
          </div>
          <div className="mt-10"><ProductWalkthrough /></div>
          <details className="mt-5 border-t border-border-subtle pt-4 text-sm text-text-secondary">
            <summary className="cursor-pointer font-semibold text-text-primary">
              Text summary of the product walkthrough
            </summary>
            <p className="mt-3 max-w-4xl leading-6">
              A fictional service-history CSV is previewed locally. SecondTrip surfaces two jobs
              at the same location and equipment, six days apart, for a manager to review. The
              manager confirms the pair as a callback and the review is added to the evidence history.
            </p>
          </details>
        </div>
      </section>

      <section id="faq" className="border-t border-border-subtle bg-surface-raised">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 sm:py-20 lg:grid-cols-[0.75fr_1.25fr]">
          <SectionHeading
            eyebrow="FAQ"
            title="Straight answers before you import anything."
            description="The private beta is intentionally narrow. These answers describe the product that exists today."
          />
          <Accordion type="single" collapsible className="border-t border-border-strong">
            {FAQS.map((item, index) => (
              <AccordionItem key={item.question} value={`faq-${index + 1}`}>
                <AccordionTrigger>{item.question}</AccordionTrigger>
                <AccordionContent><p className="leading-6">{item.answer}</p></AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </section>

      <FinalCta />
    </MarketingLayout>
  );
}

function ProofPoint({ label }: { label: string }) {
  return (
    <div className="flex items-start gap-2 text-sm font-medium text-text-primary">
      <Check className="mt-0.5 shrink-0 text-brand-primary" size={16} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function VisitPairPreview() {
  return (
    <div className="border border-border-strong bg-surface-canvas">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center border-b border-border-subtle p-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">First visit</p>
          <p className="mt-2 text-sm font-semibold text-text-primary">Service completed</p>
        </div>
        <div className="mx-3 h-px w-8 bg-brand-primary" aria-hidden="true" />
        <div className="text-right">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Return visit</p>
          <p className="mt-2 text-sm font-semibold text-text-primary">Six days later</p>
        </div>
      </div>
      <div className="space-y-4 p-5">
        <PreviewLine label="Same customer" value="Matched" />
        <PreviewLine label="Same equipment" value="Matched" />
        <PreviewLine label="Description" value="Not evaluable" />
        <div className="border-t border-border-subtle pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Decision</p>
          <p className="mt-2 text-sm font-semibold text-text-primary">Waiting for a manager review</p>
        </div>
      </div>
    </div>
  );
}

function PreviewLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-text-primary">{label}</span>
      <span className="text-text-secondary">{value}</span>
    </div>
  );
}

function ProcessStep({
  number,
  icon: Icon,
  title,
  description,
}: {
  number: string;
  icon: typeof FileUp;
  title: string;
  description: string;
}) {
  return (
    <li className="border-b border-border-subtle py-6 last:border-b-0 md:border-b-0 md:border-r md:px-6 md:first:pl-0 md:last:border-r-0 md:last:pr-0">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-brand-primary">{number}</span>
        <Icon className="text-text-secondary" size={18} aria-hidden="true" />
      </div>
      <h3 className="mt-8 text-lg font-semibold text-text-primary">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-text-secondary">{description}</p>
    </li>
  );
}

function WorkflowLine({ label, detail }: { label: string; detail: string }) {
  return (
    <li>
      <strong className="block text-text-primary">{label}</strong>
      <span className="text-text-secondary">{detail}</span>
    </li>
  );
}
