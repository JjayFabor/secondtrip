import type { ReactNode } from "react";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import { PageHero } from "@/components/marketing/page-elements";

export const LEGAL_NOTICE_UPDATED = "23 September 2026";

export function LegalPage({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <MarketingLayout>
      <PageHero
        eyebrow={eyebrow}
        title={title}
        description={description}
        aside={
          <div className="border-l-2 border-brand-primary bg-surface-canvas p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-text-secondary">
              Last updated
            </p>
            <p className="mt-2 font-semibold text-text-primary">{LEGAL_NOTICE_UPDATED}</p>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              Private-beta notice. Formal operator details are still being confirmed.
            </p>
          </div>
        }
      />
      <article className="mx-auto max-w-4xl px-6 py-14 sm:py-20">
        <div
          className="mb-10 border-l-4 border-warning bg-[var(--warning-bg)] p-5 text-text-on-accent sm:p-6"
          role="note"
          aria-labelledby="legal-draft-heading"
        >
          <p className="text-xs font-semibold uppercase tracking-widest">Document status</p>
          <h2 id="legal-draft-heading" className="mt-2 text-xl font-semibold">
            Draft for qualified legal review
          </h2>
          <p className="mt-3 text-sm leading-6">
            This page is AI-drafted and has not been reviewed by a lawyer. It is not final legal
            text or a representation that SecondTrip has completed every regulatory requirement.
          </p>
          <p className="mt-3 text-sm leading-6">
            Formal operator identity and contact details, governing jurisdiction, processing
            regions and international-transfer terms, and final retention and deletion
            obligations are still pending.
          </p>
        </div>
        {children}
      </article>
    </MarketingLayout>
  );
}

export function LegalSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="border-t border-border-subtle py-8 first:border-t-0 first:pt-0">
      <h2 className="text-2xl font-semibold tracking-tight text-text-primary">{title}</h2>
      <div className="mt-4 space-y-4 text-base leading-7 text-text-secondary">{children}</div>
    </section>
  );
}

export function LegalReviewNotice() {
  return (
    <div className="border-t border-border-subtle pt-6 text-sm leading-6 text-text-secondary">
      <strong className="text-text-primary">Next step:</strong> qualified counsel must approve
      final text and the product must implement every published promise before SecondTrip accepts
      real customer production data.
    </div>
  );
}
