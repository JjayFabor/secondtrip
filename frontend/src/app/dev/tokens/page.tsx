"use client";

import * as React from "react";
import { AlertTriangle, Check, Settings, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Logo } from "@/components/brand/logo";
import { LineChart } from "@/components/charts/line-chart";
import { HorizontalBarChart } from "@/components/charts/horizontal-bar-chart";

/**
 * /dev/tokens — visual QA reference for the design system.
 * docs/architecture/22-design-system.md is the spec; this page proves the
 * implementation matches it. Not shipped to production — see
 * PLAN.md Step 1 exit criteria.
 */

const COLOR_SWATCHES: { name: string; className: string; note?: string }[] = [
  { name: "surface-canvas", className: "bg-surface-canvas border border-border-subtle" },
  { name: "surface-raised", className: "bg-surface-raised border border-border-subtle" },
  { name: "surface-inverse", className: "bg-surface-inverse" },
  { name: "border-subtle", className: "bg-border-subtle", note: "~1.3:1 — decorative only" },
  { name: "border-strong", className: "bg-border-strong", note: "~3.2:1 — functional boundaries" },
  { name: "text-primary", className: "bg-text-primary" },
  { name: "text-secondary", className: "bg-text-secondary", note: "≥13px only" },
  { name: "brand-primary", className: "bg-brand-primary" },
  { name: "brand-deep", className: "bg-brand-deep" },
  { name: "accent", className: "bg-accent", note: "background fill only" },
  { name: "success", className: "bg-success" },
  { name: "warning", className: "bg-warning" },
  { name: "danger", className: "bg-danger" },
];

const SPACING_STEPS = [
  { token: "1", px: 4 },
  { token: "2", px: 8 },
  { token: "3", px: 12 },
  { token: "4", px: 16 },
  { token: "6", px: 24 },
  { token: "8", px: 32 },
  { token: "12", px: 48 },
  { token: "16", px: 64 },
  { token: "24", px: 96 },
];

const LINE_DATA = [
  { month: "Jan", callbacks: 14 },
  { month: "Feb", callbacks: 18 },
  { month: "Mar", callbacks: 11 },
  { month: "Apr", callbacks: 16 },
  { month: "May", callbacks: 9 },
  { month: "Jun", callbacks: 13 },
];

const BAR_DATA = [
  { label: "AC repair", value: 22 },
  { label: "Heating", value: 15 },
  { label: "Maintenance", value: 9 },
  { label: "Install", value: 4 },
];

const CANDIDATE_ROWS = [
  { pair: "Job #4821 → #4903", score: 92, band: "high", cost: 214.5 },
  { pair: "Job #4711 → #4788", score: 61, band: "medium", cost: 132.0 },
  { pair: "Job #4602 → #4655", score: 28, band: "low", cost: 0 },
];

export default function TokensPage() {
  const [dialogOpen, setDialogOpen] = React.useState(false);

  return (
    <TooltipProvider>
      <div className="mx-auto max-w-5xl px-6 py-12">
        <header className="mb-12">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Design system reference
          </p>
          <h1 className="mt-1 text-[36px] font-bold text-text-primary">SecondTrip tokens</h1>
          <p className="mt-2 max-w-2xl text-text-secondary">
            Every color, type size, spacing step, and component variant defined in{" "}
            <code className="rounded bg-surface-raised px-1.5 py-0.5 text-sm">
              docs/architecture/22-design-system.md
            </code>
            . Not shipped to production.
          </p>
        </header>

        <Section title="Color">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
            {COLOR_SWATCHES.map((s) => (
              <div key={s.name} className="flex flex-col gap-1.5">
                <div className={`h-14 rounded-[var(--radius-control)] ${s.className}`} />
                <span className="text-xs font-medium text-text-primary">{s.name}</span>
                {s.note && <span className="text-[11px] text-text-secondary">{s.note}</span>}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Typography">
          <div className="flex flex-col gap-4">
            <p className="text-[52px] font-bold leading-[1.1] text-text-primary">
              Hero 48–60 / 650–700
            </p>
            <p className="text-[40px] font-bold leading-[1.15] text-text-primary">
              H1 36–44 / 650–700
            </p>
            <p className="text-[30px] font-semibold leading-[1.2] text-text-primary">
              H2 28–32 / 600–700
            </p>
            <p className="text-[22px] font-semibold leading-[1.3] text-text-primary">
              H3 20–24 / 600
            </p>
            <p className="max-w-[34rem] text-[16px] leading-[1.6] text-text-primary">
              Body 15–16 / 400–500 — marketing paragraph measure capped at
              roughly 65–70 characters per line, which this sentence is sized to
              demonstrate.
            </p>
            <p className="text-[14px] leading-[1.5] text-text-secondary">
              Small 13–14 / 400–500
            </p>
            <p className="tabular-nums text-[28px] font-semibold text-text-primary">
              $2,481.00 <span className="text-[14px] font-normal text-text-secondary">metric / tabular-nums</span>
            </p>
          </div>
        </Section>

        <Section title="Spacing — Tailwind's default scale, unmodified">
          <div className="flex flex-col gap-2">
            {SPACING_STEPS.map((s) => (
              <div key={s.token} className="flex items-center gap-3">
                <span className="w-16 text-xs text-text-secondary">
                  {s.px}px
                </span>
                <div className={`h-3 bg-brand-primary`} style={{ width: `${s.px}px` }} />
              </div>
            ))}
          </div>
        </Section>

        <Section title="Radius & shadow">
          <div className="flex flex-wrap gap-6">
            <div className="flex flex-col items-center gap-2">
              <div className="h-16 w-16 rounded-[var(--radius-control)] border border-border-strong bg-surface-raised" />
              <span className="text-xs text-text-secondary">control — 8px</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="h-16 w-16 rounded-[var(--radius-card)] border border-border-subtle bg-surface-raised" />
              <span className="text-xs text-text-secondary">card — 12px</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="h-16 w-16 rounded-full bg-surface-raised border border-border-subtle" />
              <span className="text-xs text-text-secondary">pill — badges only</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="h-16 w-16 rounded-[var(--radius-control)] bg-surface-raised shadow-sm" />
              <span className="text-xs text-text-secondary">shadow-sm — dropdowns</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="h-16 w-16 rounded-[var(--radius-modal)] bg-surface-raised shadow-md" />
              <span className="text-xs text-text-secondary">shadow-md — dialogs</span>
            </div>
          </div>
        </Section>

        <Section title="Buttons">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="primary" disabled>
              Disabled
            </Button>
            <Button variant="primary" size="sm">
              Small
            </Button>
            <Button variant="primary" size="icon" aria-label="Settings">
              <Settings size={18} />
            </Button>
          </div>
        </Section>

        <Section title="Score band vs. review outcome — two axes, never one gradient">
          <p className="mb-4 max-w-2xl text-sm text-text-secondary">
            A high score is a strong signal, not a bad outcome — it uses brand intensity,
            never a danger color. A rejected candidate is a normal, healthy review result —
            it renders neutral, never as an error. See 22 §3.4.
          </p>
          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
                Score band (confidence)
              </p>
              <div className="flex gap-2">
                <Badge variant="neutral">Low</Badge>
                <Badge variant="warning">Medium</Badge>
                <Badge variant="strong">High</Badge>
              </div>
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
                Review outcome (human decision)
              </p>
              <div className="flex gap-2">
                <Badge variant="success">Confirmed</Badge>
                <Badge variant="neutral">Rejected</Badge>
                <Badge variant="warning">Uncertain</Badge>
              </div>
            </div>
          </div>
        </Section>

        <Section title="Form controls">
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tok-input">Customer name</Label>
              <Input id="tok-input" placeholder="Mercer Property Group" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tok-input-error">Service date</Label>
              <Input id="tok-input-error" defaultValue="13/45/2026" aria-invalid />
              <span className="text-xs text-danger">Could not parse this date.</span>
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label htmlFor="tok-textarea">Review note</Label>
              <Textarea id="tok-textarea" placeholder="Optional context for this decision…" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tok-select">Category</Label>
              <Select defaultValue="callback">
                <SelectTrigger id="tok-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="callback">Confirmed callback</SelectItem>
                  <SelectItem value="warranty">Warranty</SelectItem>
                  <SelectItem value="unrelated">Unrelated</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Checkbox id="tok-check" defaultChecked />
                <Label htmlFor="tok-check">Include suppressed candidates</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch id="tok-switch" />
                <Label htmlFor="tok-switch">AI classification enabled</Label>
              </div>
              <RadioGroup defaultValue="confirmed" className="flex gap-4">
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="confirmed" id="tok-radio-1" />
                  <Label htmlFor="tok-radio-1">Confirmed</Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="rejected" id="tok-radio-2" />
                  <Label htmlFor="tok-radio-2">Rejected</Label>
                </div>
              </RadioGroup>
            </div>
          </div>
        </Section>

        <Section title="Card">
          <Card className="max-w-sm">
            <CardHeader>
              <CardTitle>Possible Callbacks</CardTitle>
              <CardDescription>Last 30 days</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-[28px] font-semibold tabular-nums text-text-primary">24</p>
              <p className="text-sm text-text-secondary">3.8% of analyzed jobs</p>
            </CardContent>
          </Card>
        </Section>

        <Section title="Table">
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead align="right">Score</TableHead>
                  <TableHead align="right">Est. cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {CANDIDATE_ROWS.map((row) => (
                  <TableRow key={row.pair}>
                    <TableCell>{row.pair}</TableCell>
                    <TableCell align="right">
                      <Badge variant={row.band === "high" ? "strong" : row.band === "medium" ? "warning" : "neutral"}>
                        {row.score}
                      </Badge>
                    </TableCell>
                    <TableCell align="right">${row.cost.toFixed(2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </Section>

        <Section title="Tabs">
          <Tabs defaultValue="evidence" className="max-w-md">
            <TabsList>
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>
            <TabsContent value="evidence">
              <p className="text-sm text-text-secondary">Signal breakdown renders here.</p>
            </TabsContent>
            <TabsContent value="history">
              <p className="text-sm text-text-secondary">Reclassification history renders here.</p>
            </TabsContent>
          </Tabs>
        </Section>

        <Section title="Overlays">
          <div className="flex flex-wrap items-center gap-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="secondary" size="sm">
                  Hover for tooltip
                </Button>
              </TooltipTrigger>
              <TooltipContent>Same equipment, 8 days apart</TooltipContent>
            </Tooltip>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="secondary" size="sm">
                  Open popover
                </Button>
              </PopoverTrigger>
              <PopoverContent>
                <p className="text-sm text-text-primary">Filter by date range, location, service.</p>
              </PopoverContent>
            </Popover>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="secondary" size="sm">
                  Open menu
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>Actions</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <Check size={14} className="mr-2" /> Confirm
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <AlertTriangle size={14} className="mr-2" /> Flag for review
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">Open dialog</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Confirm callback</DialogTitle>
                  <DialogDescription>
                    This marks the candidate as a confirmed callback and records a cost snapshot.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={() => setDialogOpen(false)}>Confirm</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </Section>

        <Section title="Loading">
          <div className="flex max-w-sm flex-col gap-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-24 w-full" />
          </div>
        </Section>

        <Section title="Charts — brand-primary and accent only">
          <div className="grid gap-6 sm:grid-cols-2">
            <Card className="p-4">
              <p className="mb-2 text-sm font-medium text-text-primary">Callbacks over time</p>
              <LineChart data={LINE_DATA} xKey="month" series={[{ key: "callbacks", label: "Callbacks" }]} />
            </Card>
            <Card className="p-4">
              <p className="mb-2 text-sm font-medium text-text-primary">Callbacks by service</p>
              <HorizontalBarChart data={BAR_DATA} />
            </Card>
          </div>
        </Section>

        <Section title="Icons — lucide-react, 16 / 18 / 20px">
          <div className="flex items-center gap-6 text-text-primary">
            <Wrench size={16} strokeWidth={1.75} />
            <Wrench size={18} strokeWidth={1.75} />
            <Wrench size={20} strokeWidth={1.75} />
          </div>
        </Section>

        <Section title="Logo variants">
          <div className="flex flex-wrap items-center gap-6">
            <Logo variant="horizontal" />
            <Logo variant="icon" />
            <div className="rounded-[var(--radius-control)] bg-surface-inverse p-3">
              <Logo variant="dark" />
            </div>
          </div>
        </Section>
      </div>
    </TooltipProvider>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-12">
      <h2 className="mb-4 text-lg font-semibold text-text-primary">{title}</h2>
      {children}
      <Separator className="mt-12" />
    </section>
  );
}
