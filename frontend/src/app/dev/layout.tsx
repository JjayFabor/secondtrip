import type { Metadata } from "next";
import { notFound } from "next/navigation";

/**
 * Everything under /dev is internal tooling (the design-system reference
 * page, and anything similar added later) — never indexed, and stripped
 * or gated before launch per PLAN.md Step 1 exit criteria.
 */
export const metadata: Metadata = {
  title:
    process.env.NODE_ENV === "development"
      ? "Design system reference"
      : { absolute: "Page not found — SecondTrip" },
  robots: { index: false, follow: false },
};

export default function DevLayout({ children }: { children: React.ReactNode }) {
  if (process.env.NODE_ENV !== "development") {
    notFound();
  }

  return children;
}
