import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { ConfirmEmailChangeForm } from "./confirm-email-change-form";

export const metadata: Metadata = {
  title: "Confirm email change",
  robots: { index: false, follow: false },
};

export default function ConfirmEmailChangePage() {
  return (
    <AuthShell
      eyebrow="Account security"
      title="Confirm your new email"
      description="One last step will finish updating the email address on your SecondTrip account."
    >
      <Suspense fallback={<ConfirmLoadingState />}>
        <ConfirmEmailChangeForm />
      </Suspense>
    </AuthShell>
  );
}

function ConfirmLoadingState() {
  return (
    <div className="flex items-center gap-2 text-sm text-text-secondary" role="status">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-border-strong border-t-brand-primary"
        aria-hidden="true"
      />
      Preparing secure confirmation…
    </div>
  );
}
