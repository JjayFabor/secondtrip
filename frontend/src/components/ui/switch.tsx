import * as React from "react";
import { Switch as RadixSwitch } from "radix-ui";

import { cn } from "@/lib/utils";

export const Switch = React.forwardRef<
  React.ElementRef<typeof RadixSwitch.Root>,
  React.ComponentPropsWithoutRef<typeof RadixSwitch.Root>
>(({ className, ...props }, ref) => (
  <RadixSwitch.Root
    ref={ref}
    className={cn(
      "peer inline-flex h-6 w-10 shrink-0 items-center rounded-full border border-transparent",
      "bg-border-strong transition-colors duration-[var(--duration-fast)]",
      "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
      "disabled:cursor-not-allowed disabled:opacity-50",
      "data-[state=checked]:bg-brand-primary",
      className,
    )}
    {...props}
  >
    {/*
      No shadow on the thumb — depth comes from the fill/border contrast
      alone. Shadow is reserved for dropdowns, popovers, and dialogs
      (docs/architecture/22-design-system.md §5), not small controls.
    */}
    <RadixSwitch.Thumb
      className={cn(
        "block h-5 w-5 translate-x-0.5 rounded-full border border-border-subtle bg-surface-raised",
        "transition-transform duration-[var(--duration-fast)]",
        "data-[state=checked]:translate-x-[18px]",
      )}
    />
  </RadixSwitch.Root>
));
Switch.displayName = "Switch";
