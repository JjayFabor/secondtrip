import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Badge / tag / chip — the one component allowed to use --radius-pill
 * (docs/architecture/22-design-system.md §5, §9).
 *
 * `neutral` and `strong` are the two SCORE BAND treatments (§3.4) — brand
 * intensity, never an alarm color, because a high score is a strong
 * signal, not a bad outcome.
 *
 * `success` / `warning` / `danger` are REVIEW OUTCOME treatments only.
 * `rejected` review outcomes use `neutral`, never `danger` — rejecting a
 * flagged pair is a normal, healthy result of human review.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        neutral: "bg-surface-canvas text-text-secondary border border-border-strong",
        strong: "bg-brand-primary text-text-inverse",
        success: "bg-[var(--success-bg)] text-text-primary",
        warning: "bg-[var(--warning-bg)] text-text-on-accent",
        danger: "bg-[var(--danger-bg)] text-danger",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
