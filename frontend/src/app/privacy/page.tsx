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
    title: "Draft privacy notice",
    description:
      "A draft for legal review describing how SecondTrip currently handles account, test, operational, and contact-form data.",
    path: "/privacy",
  }),
  robots: { index: false, follow: false },
};

export default function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="Privacy"
      title="A plain-language account of the data SecondTrip handles."
      description="This notice separates current behavior from planned controls so private-beta users can make an informed decision."
    >
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Privacy", path: "/privacy" },
        ])}
      />
      <LegalSection id="roles" title="Proposed roles for counsel review">
        <p>
          The product has been designed around a proposed model in which SecondTrip would manage
          the limited processing needed to provide and secure accounts, while a customer
          organization would direct the use of any customer or technician information and
          SecondTrip would process it on that organization’s instructions. The legal role for
          each data category, along with responsibility for lawful bases, notices, and
          instructions, remains pending qualified counsel and operator confirmation.
        </p>
      </LegalSection>

      <LegalSection id="data" title="Data categories">
        <p>
          Account details and contact-form submissions are real personal data. SecondTrip
          processes account details to provide and secure accounts, and sends contact details and
          messages through its email provider so the operator can respond.
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Account data such as name, email, password hash, sessions, and membership.</li>
          <li>
            Private-beta test imports. These must contain only fictional or properly anonymized
            data—not real customer, technician, employee, address, phone, email, free-text note,
            or other production personal data.
          </li>
          <li>
            Derived callback candidates, signal evidence, scores, and human review decisions.
          </li>
          <li>Operational records such as audit events, task status, request IDs, and hashed IP addresses.</li>
          <li>
            Contact-form name, email, company, subject, and message. Contact messages are sent
            through the email provider and are not stored in the application database.
          </li>
        </ul>
      </LegalSection>

      <LegalSection id="purposes" title="Why data is processed">
        <p>
          SecondTrip uses data to authenticate users, isolate workspaces, import and validate job
          history, identify possible repeat visits with deterministic rules, show the supporting
          evidence, preserve review history, operate the service, prevent abuse, and respond to
          enquiries. Imported personal data is not pooled across organizations.
        </p>
      </LegalSection>

      <LegalSection id="vendors" title="Service providers">
        <p>
          SecondTrip currently relies on Neon, Render, Vercel, Cloudflare/R2, and Resend to provide
          database, API hosting, frontend hosting, DNS/object storage, and transactional email.
          See the draft <Link className="font-semibold text-brand-primary" href="/subprocessors">provider list</Link> for purposes and configuration notes. Whether each provider has a particular legal role remains part of qualified review.
        </p>
      </LegalSection>

      <LegalSection id="security" title="Security posture">
        <p>
          Current controls include encrypted HTTPS connections, scoped production credentials,
          server-side sessions, CSRF protection, forced database row-level security for tenant
          tables, organization-scoped object keys, access controls, and append-only review and
          audit records where implemented. No internet service can promise absolute security.
        </p>
      </LegalSection>

      <LegalSection id="retention" title="Retention and deletion reality">
        <p>
          The architecture defines retention periods for imported jobs, source files, raw rows,
          reviews, audit events, sessions, and operational jobs. However, scheduled retention
          purges, full organization deletion, user anonymisation, end-customer erasure tooling,
          and full organization exports are not yet implemented. Until those controls ship,
          requests are handled through the contact form and may require manual assessment.
        </p>
        <p>
          SecondTrip does not describe these planned controls as available. Private-beta users
          must not upload real production personal data. This restriction remains until
          lawyer-reviewed privacy documentation is published, the required lifecycle controls
          are implemented, and SecondTrip explicitly lifts the restriction.
        </p>
      </LegalSection>

      <LegalSection id="transfers" title="Cross-border processing">
        <p>
          Infrastructure regions and support access may involve processing outside a user’s
          country. Exact regions and legal transfer terms depend on the production configuration
          and the applicable provider agreement. Production customer data remains prohibited
          until qualified review, confirmed transfer terms, and every product launch gate are
          complete; contacting SecondTrip does not lift that restriction.
        </p>
      </LegalSection>

      <LegalSection id="rights" title="Rights and requests">
        <p>
          Account users and customer organizations may ask about access, correction, deletion,
          portability, or processing restrictions through the <Link className="font-semibold text-brand-primary" href="/contact">contact form</Link>. A final responsibility and assistance process for requests involving future production imports remains pending qualified counsel and operator confirmation.
        </p>
      </LegalSection>

      <LegalSection id="children" title="Children">
        <p>
          SecondTrip is a business operations product and is not directed to children. Users must
          not upload children’s personal data during the private beta. The fictional or properly
          anonymized test-data restriction applies without exception.
        </p>
      </LegalSection>

      <LegalSection id="changes" title="Changes and contact">
        <p>
          This notice may change as the private beta and its controls mature. The date above will
          be updated when material wording changes. Privacy and data-rights questions use the
          <Link className="font-semibold text-brand-primary" href="/contact"> contact form</Link>.
        </p>
      </LegalSection>
      <LegalReviewNotice />
    </LegalPage>
  );
}
