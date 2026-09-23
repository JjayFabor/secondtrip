import Link from "next/link";

import {
  LegalPage,
  LegalReviewNotice,
  LegalSection,
} from "@/components/marketing/legal-page";
import { JsonLd } from "@/components/seo/json-ld";
import { Button } from "@/components/ui/button";
import { breadcrumbJsonLd, pageMetadata } from "@/lib/seo";

export const metadata = {
  ...pageMetadata({
    title: "Draft DPA review",
    description:
      "A draft review path for a future SecondTrip data processing agreement during private beta.",
    path: "/dpa",
  }),
  robots: { index: false, follow: false },
};

export default function DpaPage() {
  return (
    <LegalPage
      eyebrow="Data processing agreement"
      title="Production data remains prohibited while DPA review is incomplete."
      description="SecondTrip does not publish a fabricated executed agreement. Private-beta organizations can start a scoped review through the contact form, but starting a review does not lift the data restriction."
    >
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "DPA requests", path: "/dpa" },
        ])}
      />
      <LegalSection id="roles" title="Proposed controller and processor model">
        <p>
          The product has been designed around a proposed future model in which the customer
          organization would direct the use of customer and technician information and SecondTrip
          would process it to provide the import, callback-detection, evidence, and review
          workflow. The legal role for each data category remains pending qualified counsel and
          operator confirmation.
        </p>
      </LegalSection>
      <LegalSection id="scope" title="What the review covers">
        <ul className="list-disc space-y-2 pl-6">
          <li>the categories of imported and derived data;</li>
          <li>the processing purpose, duration, and documented instructions;</li>
          <li>confidentiality and current technical controls;</li>
          <li>the current <Link className="font-semibold text-brand-primary" href="/subprocessors">subprocessor list</Link>;</li>
          <li>assistance with rights requests, deletion, and incident response; and</li>
          <li>deployment regions and transfer terms confirmed for the intended configuration.</li>
        </ul>
      </LegalSection>
      <LegalSection id="security" title="Current security controls">
        <p>
          The review can document HTTPS transport, server-side sessions, CSRF protection, scoped
          secrets, forced row-level security for tenant tables, tenant-scoped repositories,
          private object storage, access controls, and auditability. It must also record that
          automated organization deletion, user anonymisation, full exports, end-customer erasure,
          and scheduled retention purges are not yet complete.
        </p>
      </LegalSection>
      <LegalSection id="incidents" title="Incident path">
        <p>
          Suspected incidents should be reported through the contact form with “Security incident”
          in the subject. Do not include passwords, customer records, or other sensitive evidence
          in the initial message. SecondTrip will use the supplied reply address to coordinate
          containment and assessment.
        </p>
      </LegalSection>
      <LegalSection id="request" title="How to request a DPA">
        <p>
          Use the contact form with “DPA request” as the subject. Include the organization name,
          intended data categories, expected dataset size, and any required review deadline. The
          response will confirm what documentation is currently available and what must be resolved
          before production data can be accepted. Submitting a request does not authorize an
          organization to upload production data.
        </p>
        <Button asChild className="mt-2">
          <Link href="/contact">Start a DPA request</Link>
        </Button>
      </LegalSection>
      <LegalReviewNotice />
    </LegalPage>
  );
}
