"use client";

import { Activity, ArrowRight, Check, Users } from "lucide-react";
import Link from "next/link";

import { useAppShell } from "@/components/dashboard/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { User } from "@/lib/api";

export function DashboardHome() {
  const { user } = useAppShell();
  return <DashboardContent user={user} />;
}

function DashboardContent({ user }: { user: User }) {
  const firstName = user.full_name.trim().split(/\s+/)[0] || "there";

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <header className="flex flex-col gap-4 border-b border-border-subtle pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Badge variant="neutral">Demo workspace · no live data</Badge>
          <h1 className="mt-4 text-[30px] font-bold leading-tight text-text-primary sm:text-[36px]">
            Welcome back, {firstName}.
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
            Your operating rhythm is ready. Connect a source when you want to turn this empty
            canvas into a useful team conversation.
          </p>
        </div>
        <Button asChild variant="secondary">
          <Link href="#setup">
            Review setup
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </Button>
      </header>

      <section aria-labelledby="summary-heading">
        <div className="mb-3 flex items-center justify-between gap-4">
          <h2 id="summary-heading" className="text-lg font-semibold text-text-primary">
            At a glance
          </h2>
          <span className="text-xs text-text-secondary">Waiting for your first source</span>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard label="Callback signals" value="—" description="No source connected" />
          <SummaryCard label="In review" value="—" description="Nothing waiting yet" />
          <SummaryCard label="Prevented repeat work" value="—" description="Available after review" />
        </div>
      </section>

      <section id="setup" className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
                The operating rhythm
              </p>
              <h2 className="mt-2 text-xl font-semibold text-text-primary">Signal → review → prevent</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">
                Every useful insight should end in a team action. This strip will become the
                center of your workspace once your first activity source is connected.
              </p>
            </div>
            <Activity className="hidden shrink-0 text-brand-primary sm:block" size={22} aria-hidden="true" />
          </div>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            <RailStep index="01" title="Signal" description="Find a pattern" state="ready" />
            <RailStep index="02" title="Review" description="Add context" state="next" />
            <RailStep index="03" title="Prevent" description="Capture the lesson" state="later" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-[var(--warning-bg)] text-text-on-accent">
              <Users size={18} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-text-primary">What to do next</h2>
              <p className="mt-1 text-sm leading-6 text-text-secondary">
                Set up the smallest useful loop for your team.
              </p>
            </div>
          </div>
          <ul className="mt-6 space-y-4">
            <NextStep title="Connect a source" description="Bring in the work your team already tracks." />
            <NextStep title="Invite one teammate" description="Make the first review a shared conversation." />
            <NextStep title="Review your first signal" description="Decide what a better first visit looks like." />
          </ul>
        </Card>
      </section>

      <section aria-labelledby="activity-heading">
        <div className="mb-3 flex items-center justify-between gap-4">
          <div>
            <h2 id="activity-heading" className="text-lg font-semibold text-text-primary">
              Recent activity
            </h2>
            <p className="mt-1 text-sm text-text-secondary">A transparent starting point for this demo workspace.</p>
          </div>
          <Badge variant="neutral">Demo only</Badge>
        </div>
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Activity</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>State</TableHead>
                <TableHead align="right">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>
                  <p className="font-medium">Workspace created</p>
                  <p className="mt-0.5 text-xs text-text-secondary">Ready for your first source</p>
                </TableCell>
                <TableCell>{user.full_name}</TableCell>
                <TableCell>
                  <Badge variant="success">Ready</Badge>
                </TableCell>
                <TableCell align="right">Today</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>
                  <p className="font-medium">No live activity yet</p>
                  <p className="mt-0.5 text-xs text-text-secondary">This row will fill after setup</p>
                </TableCell>
                <TableCell>—</TableCell>
                <TableCell>
                  <Badge variant="neutral">Waiting</Badge>
                </TableCell>
                <TableCell align="right">—</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </section>
    </div>
  );
}

function SummaryCard({ label, value, description }: { label: string; value: string; description: string }) {
  return (
    <Card className="p-5">
      <p className="text-sm font-medium text-text-secondary">{label}</p>
      <p className="tabular-nums mt-4 text-[32px] font-semibold leading-none text-text-primary">{value}</p>
      <p className="mt-3 text-xs text-text-secondary">{description}</p>
    </Card>
  );
}

function RailStep({
  index,
  title,
  description,
  state,
}: {
  index: string;
  title: string;
  description: string;
  state: "ready" | "next" | "later";
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border-subtle bg-surface-canvas p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold tracking-[0.14em] text-text-secondary">{index}</span>
        <span
          className={
            state === "ready"
              ? "h-2.5 w-2.5 rounded-full bg-brand-primary"
              : state === "next"
                ? "h-2.5 w-2.5 rounded-full bg-accent"
                : "h-2.5 w-2.5 rounded-full bg-border-strong"
          }
          aria-hidden="true"
        />
      </div>
      <p className="mt-7 text-sm font-semibold text-text-primary">{title}</p>
      <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
    </div>
  );
}

function NextStep({ title, description }: { title: string; description: string }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border-strong text-brand-primary">
        <Check size={12} strokeWidth={2.5} aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-medium text-text-primary">{title}</p>
        <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
      </div>
    </li>
  );
}
