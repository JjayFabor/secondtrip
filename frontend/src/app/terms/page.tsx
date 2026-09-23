import Link from "next/link";

import {
  LegalPage,
  LegalReviewNotice,
  LegalSection,
} from "@/components/marketing/legal-page";
import { JsonLd } from "@/components/seo/json-ld";
import { breadcrumbJsonLd, pageMetadata } from "@/lib/seo";

export const metadata = {
  ...pageMetadata({
    title: "Draft private-beta terms",
    description: "Draft terms for qualified legal review of the SecondTrip private beta.",
    path: "/terms",
  }),
  robots: { index: false, follow: false },
};

export default function TermsPage() {
  return (
    <LegalPage
      eyebrow="Terms"
      title="Private-beta terms built around responsible evaluation."
      description="SecondTrip is currently free beta software. These terms describe the practical expectations while formal operator details are being completed."
    >
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Terms", path: "/terms" },
        ])}
      />
      <LegalSection id="eligibility" title="Eligibility and authority">
        <p>
          You must be able to enter an agreement for yourself or the organization you represent.
          If you create a workspace for an organization, you confirm that you have authority to
          do so and to invite its members.
        </p>
      </LegalSection>
      <LegalSection id="accounts" title="Accounts and security">
        <p>
          Provide accurate account information, keep credentials confidential, and notify
          SecondTrip through the contact form if you suspect unauthorized access. You are
          responsible for activity performed through accounts you control.
        </p>
      </LegalSection>
      <LegalSection id="customer-data" title="Customer data responsibility">
        <p>
          Private-beta imports are limited to fictional or properly anonymized test data. You must
          not upload real customer, technician, employee, address, phone, email, free-text note,
          or other production personal data. This restriction remains until SecondTrip publishes
          lawyer-reviewed terms and privacy documentation and explicitly lifts the restriction.
        </p>
      </LegalSection>
      <LegalSection id="acceptable-use" title="Acceptable use">
        <p>You must not use SecondTrip to:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>break applicable law or another person’s rights;</li>
          <li>probe, disrupt, overload, or bypass the service’s security controls;</li>
          <li>upload malware or data you are not authorized to process;</li>
          <li>
            upload real production personal data while the private-beta data restriction remains
            in place; or
          </li>
          <li>treat an unreviewed candidate score as a final employment or customer decision.</li>
        </ul>
      </LegalSection>
      <LegalSection id="beta" title="Beta availability and changes">
        <p>
          The service is experimental and may change, pause, or stop. Features and limits may be
          adjusted for design partners, and payment processing is not enabled. Final commitments
          concerning availability, support, data preservation, or any future offering remain
          pending qualified counsel and operator confirmation.
        </p>
      </LegalSection>
      <LegalSection id="ip" title="Intellectual property and feedback">
        <p>
          You keep ownership of your data. SecondTrip retains ownership of the service, software,
          design, and documentation. You may provide feedback voluntarily; SecondTrip may use it
          to improve the product without claiming ownership of your underlying business data.
        </p>
      </LegalSection>
      <LegalSection id="confidentiality" title="Confidentiality">
        <p>
          Each party should protect non-public information received from the other and use it only
          for the beta relationship, except where disclosure is authorized or legally required.
          Do not submit highly sensitive information through the contact form.
        </p>
      </LegalSection>
      <LegalSection id="termination" title="Suspension and termination">
        <p>
          You may stop using the beta at any time and request account or workspace handling through
          the contact form. SecondTrip may suspend access for security, abuse, legal risk, or beta
          closure. Automated organization deletion and export workflows are not yet available.
        </p>
      </LegalSection>
      <LegalSection id="disclaimers" title="Product limits and pending legal terms">
        <p>
          SecondTrip surfaces possible callbacks using deterministic evidence; it does not make
          the final classification and does not replace professional operational judgment. A
          manager must review each surfaced pair because the product can miss a repeat visit or
          surface a pair that is not a callback.
        </p>
        <p>
          Final warranty, disclaimer, liability, indemnity, and risk-allocation terms have not
          been decided. Qualified counsel and the operator must confirm them before final terms
          are published.
        </p>
      </LegalSection>
      <LegalSection id="law" title="Applicable law and contact">
        <p>
          Governing law, venue, dispute process, and the treatment of mandatory law remain pending
          qualified counsel and operator confirmation. Questions about these draft terms use the
          <Link className="font-semibold text-brand-primary" href="/contact"> contact form</Link>.
        </p>
      </LegalSection>
      <LegalReviewNotice />
    </LegalPage>
  );
}
