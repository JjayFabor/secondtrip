import Link from "next/link";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import { PageHero } from "@/components/marketing/page-elements";
import { JsonLd } from "@/components/seo/json-ld";
import { breadcrumbJsonLd, pageMetadata } from "@/lib/seo";
import { ContactForm } from "./contact-form";

export const metadata = pageMetadata({
  title: "Contact",
  description:
    "Contact SecondTrip about support, privacy, a data processing agreement, or joining the private beta.",
  path: "/contact",
});

export default function ContactPage() {
  return (
    <MarketingLayout>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Contact", path: "/contact" },
        ])}
      />
      <PageHero
        eyebrow="Contact"
        title="Start with the question your team actually has."
        description="Use this form for product support, private-beta enquiries, privacy requests, or a DPA discussion. Messages are sent directly to SecondTrip and are not stored in the application database."
      />
      <section className="mx-auto grid max-w-6xl gap-12 px-6 py-16 sm:py-20 lg:grid-cols-[0.7fr_1.3fr]">
        <aside>
          <h2 className="text-xl font-semibold text-text-primary">One route for now</h2>
          <p className="mt-3 text-sm leading-6 text-text-secondary">
            The private beta keeps support simple. Choose a clear subject and SecondTrip will
            route the request appropriately.
          </p>
          <ul className="mt-6 space-y-4 border-l-2 border-brand-primary pl-5 text-sm text-text-secondary">
            <li>
              <strong className="block text-text-primary">Product and support</strong>
              Questions about imports, review workflow, or fit.
            </li>
            <li>
              <strong className="block text-text-primary">Privacy and data rights</strong>
              Account or processing requests and questions.
            </li>
            <li>
              <strong className="block text-text-primary">DPA requests</strong>
              Start the private-beta review process described on the{" "}
              <Link className="font-semibold text-brand-primary" href="/dpa">
                DPA page
              </Link>
              .
            </li>
          </ul>
        </aside>
        <div className="border border-border-strong bg-surface-raised p-5 sm:p-8">
          <h2 className="text-2xl font-semibold text-text-primary">Send a message</h2>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            All fields are required unless marked optional.
          </p>
          <div className="mt-7">
            <ContactForm />
          </div>
          <p className="mt-6 border-t border-border-subtle pt-5 text-xs leading-5 text-text-secondary">
            Your contact details and message are used only to respond to this enquiry and are
            sent through the email provider. See the draft{" "}
            <Link className="font-semibold text-brand-primary" href="/privacy">
              privacy notice
            </Link>
            . Submitting this form is not consent to unrelated processing.
          </p>
        </div>
      </section>
    </MarketingLayout>
  );
}
