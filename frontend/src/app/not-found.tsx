import type { Metadata } from "next";
import Link from "next/link";

import { MarketingLayout } from "@/components/marketing/marketing-layout";
import { Eyebrow } from "@/components/marketing/page-elements";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: { absolute: "Page not found — SecondTrip" },
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <MarketingLayout>
      <section className="bg-surface-canvas">
        <div className="mx-auto max-w-6xl px-6 py-16 sm:py-24">
          <div className="max-w-xl">
            <Eyebrow>404</Eyebrow>
            <h1 className="mt-4 text-4xl font-bold leading-tight tracking-tight text-text-primary sm:text-5xl">
              Page not found
            </h1>
            <p className="mt-5 text-base leading-7 text-text-secondary">
              The link may be outdated, or the address may have been mistyped.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
              <Button asChild size="lg">
                <Link href="/">Return home</Link>
              </Button>
              <Link
                href="/contact"
                className="rounded-[var(--radius-control)] text-sm font-semibold text-brand-primary underline decoration-border-strong underline-offset-4 transition-colors duration-[var(--duration-fast)] hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
              >
                Contact support
              </Link>
            </div>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
