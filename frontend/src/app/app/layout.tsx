import type { Metadata } from "next";

import { AppShell } from "@/components/dashboard/app-shell";
import { getAuthenticatedBootstrap } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default async function AuthenticatedAppLayout({ children }: { children: React.ReactNode }) {
  const { user, organizations } = await getAuthenticatedBootstrap();
  return <AppShell user={user} organizations={organizations}>{children}</AppShell>;
}
