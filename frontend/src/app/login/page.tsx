import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Sign in — SecondTrip",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to SecondTrip"
      description="Pick up the operating rhythm for your team and see what needs a closer look."
    >
      <LoginForm />
    </AuthShell>
  );
}
