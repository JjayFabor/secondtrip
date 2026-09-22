import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ForgotPasswordForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Reset your password — SecondTrip",
};

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      eyebrow="Account access"
      title="Reset your password"
      description="Enter your account email and we’ll send a short-lived link to make a new password."
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}
