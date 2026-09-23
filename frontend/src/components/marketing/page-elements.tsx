import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-widest text-brand-primary">
      {children}
    </p>
  );
}

export function PageHero({
  eyebrow,
  title,
  description,
  aside,
}: {
  eyebrow: string;
  title: string;
  description: string;
  aside?: ReactNode;
}) {
  return (
    <section className="border-b border-border-subtle bg-surface-raised">
      <div className="mx-auto grid max-w-6xl gap-10 px-6 py-14 sm:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-end lg:gap-16">
        <div>
          <Eyebrow>{eyebrow}</Eyebrow>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-tight tracking-tight text-text-primary sm:text-5xl">
            {title}
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-text-secondary">{description}</p>
        </div>
        {aside ? <div>{aside}</div> : <VisitTrail compact />}
      </div>
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-3 text-3xl font-bold leading-tight tracking-tight text-text-primary sm:text-4xl">
        {title}
      </h2>
      {description ? (
        <p className="mt-4 text-base leading-7 text-text-secondary">{description}</p>
      ) : null}
    </div>
  );
}

export function VisitTrail({ compact = false }: { compact?: boolean }) {
  const steps = [
    { label: "First visit", detail: "Imported job history" },
    { label: "Return visit", detail: "Possible callback surfaced" },
    { label: "Human review", detail: "Decision recorded" },
  ];
  return (
    <ol
      aria-label="SecondTrip workflow"
      className="border-l-2 border-brand-primary bg-surface-canvas px-5 py-4"
    >
      {steps.map((step, index) => (
        <li
          key={step.label}
          className={index === steps.length - 1 ? "relative pl-6" : "relative pb-5 pl-6"}
        >
          <span
            className="absolute -left-7 top-1 h-3 w-3 rounded-full border-2 border-brand-primary bg-surface-raised"
            aria-hidden="true"
          />
          <p className="text-sm font-semibold text-text-primary">{step.label}</p>
          {!compact || index === 2 ? (
            <p className="mt-1 text-sm text-text-secondary">{step.detail}</p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function CheckList({ items }: { items: readonly string[] }) {
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item} className="flex gap-3 text-sm leading-6 text-text-secondary">
          <Check className="mt-1 shrink-0 text-brand-primary" size={16} aria-hidden="true" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function FinalCta({
  title = "Bring your job history. Keep your existing system.",
  description = "Start a free private-beta workspace using only fictional or properly anonymized test data. Real production personal data is not permitted yet.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <section className="border-t border-border-subtle bg-surface-inverse text-text-inverse">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-12 sm:flex-row sm:items-center sm:justify-between sm:py-16">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-text-inverse">Private beta</p>
          <h2 className="mt-2 text-2xl font-semibold leading-tight sm:text-3xl">{title}</h2>
          <p className="mt-3 text-sm leading-6 text-text-inverse">{description}</p>
        </div>
        <Button asChild variant="secondary" size="lg">
          <Link href="/register">
            Try SecondTrip
            <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </Button>
      </div>
    </section>
  );
}
