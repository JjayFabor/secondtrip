import Link from "next/link";

import { Logo } from "@/components/brand/logo";

/**
 * Temporary placeholder. The real marketing homepage is built in
 * PLAN.md Step 8, on top of the design system shipped here in Step 1.
 * This page exists only so the app has a real root route to boot on.
 */
export default function Home() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <Logo variant="horizontal" />
      <p className="max-w-sm text-sm text-text-secondary">
        Design system foundation. The marketing homepage and dashboard are built in later
        phases — see{" "}
        <Link href="/dev/tokens" className="font-medium text-brand-primary hover:underline">
          /dev/tokens
        </Link>{" "}
        for the component reference.
      </p>
    </main>
  );
}
