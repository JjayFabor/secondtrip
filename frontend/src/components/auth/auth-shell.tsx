import type { ReactNode } from "react";

import { CircleAlert, CircleCheck } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-surface-canvas">
      <header className="flex h-16 items-center border-b border-border-subtle bg-surface-raised px-4 sm:px-6">
        <Link href="/" aria-label="SecondTrip home">
          <Logo variant="horizontal" />
        </Link>
      </header>

      <main className="flex flex-1 items-start justify-center px-4 py-10 sm:items-center sm:py-16">
        <Card className="w-full max-w-md">
          <div className="p-6 sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
              {eyebrow}
            </p>
            <h1 className="mt-3 text-[30px] font-bold leading-tight text-text-primary">
              {title}
            </h1>
            <p className="mt-3 text-sm leading-6 text-text-secondary">{description}</p>
            <div className="mt-7">{children}</div>
          </div>
        </Card>
      </main>

      <p className="px-4 pb-6 text-center text-xs text-text-secondary">
        Calm operations for teams that want fewer repeat visits.
      </p>
    </div>
  );
}

export function FormAlert({
  kind,
  children,
}: {
  kind: "error" | "success";
  children: ReactNode;
}) {
  const isError = kind === "error";
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-[var(--radius-control)] border px-3 py-2.5 text-sm leading-5",
        isError
          ? "border-danger bg-[var(--danger-bg)] text-danger"
          : "border-success bg-[var(--success-bg)] text-success",
      )}
      role={isError ? "alert" : "status"}
    >
      {isError ? (
        <CircleAlert className="mt-0.5 shrink-0" size={16} aria-hidden="true" />
      ) : (
        <CircleCheck className="mt-0.5 shrink-0" size={16} aria-hidden="true" />
      )}
      <span>{children}</span>
    </div>
  );
}

export function AuthDivider({ children }: { children: ReactNode }) {
  return (
    <div className="mt-6 flex items-center gap-3 text-sm text-text-secondary">
      <span className="h-px flex-1 bg-border-subtle" />
      <span>{children}</span>
      <span className="h-px flex-1 bg-border-subtle" />
    </div>
  );
}
