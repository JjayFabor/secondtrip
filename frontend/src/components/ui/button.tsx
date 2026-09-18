import * as React from "react";
import { Slot } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Button variants — docs/architecture/22-design-system.md §9.
 *
 * primary     teal fill, white text — the one primary action per view
 * secondary   raised surface, deep-petrol text, strong border
 * destructive danger fill, white text — reserved, irreversible actions only
 * ghost       no fill, canvas on hover — low-emphasis actions
 *
 * Never pill-shaped (§5) — radius is --radius-control (8px) at every size.
 */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "rounded-[var(--radius-control)] text-[15px] font-semibold",
    "transition-colors duration-[var(--duration-fast)] ease-[var(--easing-out)]",
    "disabled:pointer-events-none disabled:opacity-50",
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
  ].join(" "),
  {
    variants: {
      variant: {
        primary: [
          "bg-brand-primary text-text-inverse",
          "hover:bg-[var(--brand-primary-hover)] active:bg-[var(--brand-primary-active)]",
        ].join(" "),
        secondary: [
          "bg-surface-raised text-brand-deep border border-border-strong",
          "hover:bg-surface-canvas",
        ].join(" "),
        destructive: ["bg-danger text-text-inverse", "hover:opacity-90"].join(" "),
        ghost: ["bg-transparent text-text-primary", "hover:bg-surface-canvas"].join(" "),
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3 text-sm",
        lg: "h-11 px-6",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render as the child element (e.g. a Next.js `<Link>`) instead of a `<button>`. */
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot.Root : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
