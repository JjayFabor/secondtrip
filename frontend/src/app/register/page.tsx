import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { RegisterForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Create an account — SecondTrip",
};

export default function RegisterPage() {
  return (
    <AuthShell
      eyebrow="Start with a clear signal"
      title="Create your workspace"
      description="Set up a calm place for your team to understand callbacks and improve the next visit."
    >
      <RegisterForm />
    </AuthShell>
  );
}
