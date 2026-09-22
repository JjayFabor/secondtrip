import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { VerifyForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Verify your email — SecondTrip",
};

export default function VerifyPage() {
  return (
    <AuthShell
      eyebrow="One last step"
      title="Verify your email"
      description="Use the token from your verification email. The local development server prints it in the API console."
    >
      <Suspense fallback={<p className="text-sm text-text-secondary">Loading verification link…</p>}>
        <VerifyForm />
      </Suspense>
    </AuthShell>
  );
}
