import type { Metadata } from "next";

/**
 * Everything under /dev is internal tooling (the design-system reference
 * page, and anything similar added later) — never indexed, and stripped
 * or gated before launch per PLAN.md Step 1 exit criteria.
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default function DevLayout({ children }: { children: React.ReactNode }) {
  return children;
}
