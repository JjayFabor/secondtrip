import type { ReactNode } from "react";

import { Footer } from "@/components/marketing/footer";
import { Nav } from "@/components/marketing/nav";

export function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <Nav />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
