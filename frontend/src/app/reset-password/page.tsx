import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Choose a new password — SecondTrip",
  robots: { index: false, follow: false },
};

export default function ResetPasswordPage() {
  return (
    <AuthShell
      eyebrow="Account access"
      title="Choose a new password"
      description="Use the short-lived reset token from your email, then you’ll be signed in automatically."
    >
      <Suspense fallback={<p className="text-sm text-text-secondary">Loading reset link…</p>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
