import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { AcceptInviteForm } from "./accept-invite-form";

export const metadata: Metadata = {
  title: "Accept invitation — SecondTrip",
  robots: { index: false, follow: false },
};

export default function AcceptInvitePage() {
  return (
    <AuthShell
      eyebrow="Invitation"
      title="Join your team on SecondTrip"
      description="Review the invitation details, then accept when you’re ready to join the workspace."
    >
      <Suspense fallback={<InviteLoadingState />}>
        <AcceptInviteForm />
      </Suspense>
    </AuthShell>
  );
}

function InviteLoadingState() {
  return (
    <div className="flex items-center gap-2 text-sm text-text-secondary" role="status">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-border-strong border-t-brand-primary"
        aria-hidden="true"
      />
      Checking your invitation…
    </div>
  );
}
