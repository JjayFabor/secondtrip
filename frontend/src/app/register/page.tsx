import type { Metadata } from "next";
import Link from "next/link";

import { AuthShell } from "@/components/auth/auth-shell";
import { RegisterForm } from "@/components/auth/auth-forms";

export const metadata: Metadata = {
  title: "Create an account",
  robots: { index: false, follow: false },
};

export default function RegisterPage() {
  return (
    <AuthShell
      eyebrow="Start with a clear signal"
      title="Create your workspace"
      description="Set up a calm place for your team to understand callbacks and improve the next visit."
    >
      <div className="border-l-4 border-warning bg-[var(--warning-bg)] p-4 text-sm leading-6 text-text-on-accent">
        <p className="font-semibold">Private-beta data restriction</p>
        <p className="mt-1">
          Use only fictional or properly anonymized test data. Do not upload real customer,
          technician, employee, address, phone, email, free-text note, or other production
          personal data.
        </p>
        <p className="mt-2 text-xs">
          Read the draft{" "}
          <Link className="font-semibold underline" href="/privacy">privacy notice</Link>
          {" "}and draft{" "}
          <Link className="font-semibold underline" href="/terms">terms</Link>.
        </p>
      </div>
      <RegisterForm />
    </AuthShell>
  );
}
