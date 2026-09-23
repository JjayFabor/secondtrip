import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import { CheckList, PageHero, SectionHeading } from "@/components/marketing/page-elements";
import { JsonLd } from "@/components/seo/json-ld";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { breadcrumbJsonLd, pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Pricing",
  description:
    "SecondTrip is currently a free private beta with clear baseline limits and no payment processing.",
  path: "/pricing",
});

export default function PricingPage() {
  return (
    <MarketingLayout>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Pricing", path: "/pricing" },
        ])}
      />
      <PageHero
        eyebrow="Pricing"
        title="One honest offer while the product is in private beta."
        description="SecondTrip is free to use during the private beta. Payment processing is not enabled, and there is no paid plan to choose today."
        aside={
          <div className="border-l-2 border-brand-primary bg-surface-canvas p-6">
            <Badge variant="neutral">Private beta</Badge>
            <p className="mt-5 text-4xl font-bold tracking-tight text-text-primary">Free</p>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              No card, checkout, or subscription setup.
            </p>
          </div>
        }
      />

      <section className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
        <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHeading
            eyebrow="Current boundaries"
            title="Enough room to test a realistic operating workflow."
            description="These are the implemented free-tier defaults. Limits may be adjusted for design partners as SecondTrip learns from responsible private-beta use."
          />
          <div className="grid gap-8 border-t border-border-strong pt-8 sm:grid-cols-2">
            <CheckList
              items={[
                "Up to 5,000 imported jobs per month",
                "Up to 10,000 jobs retained",
                "Three imports per month",
                "One import processing at a time",
              ]}
            />
            <CheckList
              items={[
                "CSV files up to 5 MB",
                "Two workspace members",
                "Six months of job retention",
                "Up to five exports per month",
              ]}
            />
          </div>
        </div>
      </section>

      <section className="border-y border-border-subtle bg-surface-raised">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-14 sm:grid-cols-2 sm:py-16">
          <div>
            <h2 className="text-2xl font-semibold text-text-primary">What may change</h2>
            <p className="mt-3 text-base leading-7 text-text-secondary">
              Beta limits, feature availability, and the future commercial model may change as the
              product matures. Existing data is not deleted because a future paid plan is introduced.
            </p>
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-text-primary">Need a different test shape?</h2>
            <p className="mt-3 text-base leading-7 text-text-secondary">
              If your sample exceeds a current limit, contact SecondTrip before importing it. A design-partner adjustment may be possible.
            </p>
            <Link className="mt-5 inline-flex items-center gap-2 font-semibold text-brand-primary" href="/contact">
              Discuss your dataset <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      <section className="bg-surface-inverse text-text-inverse">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-12 sm:flex-row sm:items-center sm:justify-between sm:py-16">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-text-inverse">Start free</p>
            <h2 className="mt-2 text-3xl font-semibold">Try the workflow with your team.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-text-inverse">
              Private-beta workspaces may use only fictional or properly anonymized test data.
              Do not upload real production personal data.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button asChild variant="secondary"><Link href="/contact">Contact us</Link></Button>
            <Button asChild><Link href="/register">Create a workspace</Link></Button>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
