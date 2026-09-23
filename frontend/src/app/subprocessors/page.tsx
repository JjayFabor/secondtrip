import Link from "next/link";

import { LegalPage, LegalReviewNotice } from "@/components/marketing/legal-page";
import { JsonLd } from "@/components/seo/json-ld";
import { breadcrumbJsonLd, pageMetadata } from "@/lib/seo";

export const metadata = {
  ...pageMetadata({
    title: "Draft subprocessor list",
    description:
      "A draft for legal review of the infrastructure and email providers used by SecondTrip.",
    path: "/subprocessors",
  }),
  robots: { index: false, follow: false },
};

const SUBPROCESSORS = [
  {
    provider: "Neon",
    purpose: "Managed PostgreSQL database",
    data: "Account, workspace, imported job, derived evidence, review, and operational records",
  },
  {
    provider: "Render",
    purpose: "FastAPI hosting and background processing",
    data: "API requests and data processed by the application",
  },
  {
    provider: "Vercel",
    purpose: "Public website and application frontend hosting",
    data: "Frontend requests and server-rendered application responses",
  },
  {
    provider: "Cloudflare / R2",
    purpose: "DNS and private object storage",
    data: "DNS requests, import source files, generated reports, and exports when implemented",
  },
  {
    provider: "Resend",
    purpose: "Transactional and contact-form email delivery",
    data: "Recipient addresses and rendered email content needed for delivery",
  },
] as const;

export default function SubprocessorsPage() {
  return (
    <LegalPage
      eyebrow="Subprocessors"
      title="The services that help operate SecondTrip."
      description="This list covers the current private-beta infrastructure. Provider regions and configuration may vary by deployment."
    >
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Subprocessors", path: "/subprocessors" },
        ])}
      />
      <div
        className="overflow-x-auto border border-border-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
        role="region"
        tabIndex={0}
        aria-label="Subprocessor table. Use the arrow keys to scroll horizontally and review every column."
      >
        <table className="w-full min-w-3xl border-collapse text-left text-sm">
          <caption className="sr-only">Current SecondTrip subprocessors and their purposes</caption>
          <thead className="bg-surface-canvas text-text-primary">
            <tr>
              <th scope="col" className="border-b border-border-strong px-4 py-3 font-semibold">Provider</th>
              <th scope="col" className="border-b border-border-strong px-4 py-3 font-semibold">Purpose</th>
              <th scope="col" className="border-b border-border-strong px-4 py-3 font-semibold">Data involved</th>
            </tr>
          </thead>
          <tbody className="bg-surface-raised text-text-secondary">
            {SUBPROCESSORS.map((item) => (
              <tr key={item.provider}>
                <th scope="row" className="border-b border-border-subtle px-4 py-4 align-top font-semibold text-text-primary">
                  {item.provider}
                </th>
                <td className="border-b border-border-subtle px-4 py-4 align-top leading-6">{item.purpose}</td>
                <td className="border-b border-border-subtle px-4 py-4 align-top leading-6">{item.data}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-8 space-y-4 text-base leading-7 text-text-secondary">
        <p>
          This page intentionally does not state exact legal entities, processing regions, or
          transfer mechanisms until those details are confirmed against the active provider
          agreements and deployment configuration.
        </p>
        <p>
          Ask for current configuration details or start a DPA review through the
          <Link className="font-semibold text-brand-primary" href="/contact"> contact form</Link>.
        </p>
      </div>
      <div className="mt-8"><LegalReviewNotice /></div>
    </LegalPage>
  );
}
