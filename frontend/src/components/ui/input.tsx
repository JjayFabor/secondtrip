import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Input — uses --border-strong, not the default subtle border, because an
 * input's edge must read as a boundary on its own (WCAG 1.4.11, ~3.2:1).
 * See docs/architecture/22-design-system.md §3.3.
 */
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          "flex h-10 w-full rounded-[var(--radius-control)] border border-border-strong",
          "bg-surface-raised px-3 text-[15px] text-text-primary placeholder:text-text-secondary",
          "transition-colors duration-[var(--duration-fast)]",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "aria-invalid:border-danger",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";
