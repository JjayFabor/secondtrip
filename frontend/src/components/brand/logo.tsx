import { cn } from "@/lib/utils";

/**
 * Logo — a temporary wordmark until the open-loop S mark exists
 * (docs/architecture/22-design-system.md §7). `variant="icon"` reserves
 * the future mark's slot rather than fabricating a placeholder symbol —
 * see 22 §7's explicit ban list (no airplane/pin/truck/wrench/refresh/
 * infinity/sparkle icon).
 */
export type LogoVariant = "horizontal" | "icon" | "mono" | "dark";

export interface LogoProps {
  variant?: LogoVariant;
  className?: string;
}

export function Logo({ variant = "horizontal", className }: LogoProps) {
  const isInverse = variant === "dark";

  if (variant === "icon") {
    // Reserved slot for the open-loop S mark. Renders the wordmark's
    // initial until that asset ships — never a fabricated substitute icon.
    return (
      <span
        aria-label="SecondTrip"
        className={cn(
          "inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)]",
          "bg-brand-deep text-[17px] font-bold text-text-inverse",
          className,
        )}
      >
        S
      </span>
    );
  }

  return (
    <span
      className={cn(
        "font-sans text-[19px] font-bold tracking-tight",
        isInverse ? "text-text-inverse" : variant === "mono" ? "text-current" : "text-brand-deep",
        className,
      )}
    >
      SecondTrip
    </span>
  );
}
