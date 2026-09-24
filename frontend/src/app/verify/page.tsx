import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { VerifyForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Verify your email",
  robots: { index: false, follow: false },
};

export default function VerifyPage() {
  return (
    <AuthShell
      eyebrow="One last step"
      title="Verify your email"
      description="Use the secure link in your verification email to finish setting up your account."
    >
      <Suspense fallback={<p className="text-sm text-text-secondary">Loading verification link…</p>}>
        <VerifyForm />
      </Suspense>
    </AuthShell>
  );
}
