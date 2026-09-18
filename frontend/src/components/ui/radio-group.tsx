import * as React from "react";
import { RadioGroup as RadixRadioGroup } from "radix-ui";

import { cn } from "@/lib/utils";

export const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadixRadioGroup.Root>,
  React.ComponentPropsWithoutRef<typeof RadixRadioGroup.Root>
>(({ className, ...props }, ref) => (
  <RadixRadioGroup.Root ref={ref} className={cn("grid gap-2", className)} {...props} />
));
RadioGroup.displayName = "RadioGroup";

export const RadioGroupItem = React.forwardRef<
  React.ElementRef<typeof RadixRadioGroup.Item>,
  React.ComponentPropsWithoutRef<typeof RadixRadioGroup.Item>
>(({ className, ...props }, ref) => (
  <RadixRadioGroup.Item
    ref={ref}
    className={cn(
      "aspect-square h-4 w-4 rounded-full border border-border-strong bg-surface-raised",
      "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    <RadixRadioGroup.Indicator className="flex h-full w-full items-center justify-center">
      <span className="h-2 w-2 rounded-full bg-brand-primary" />
    </RadixRadioGroup.Indicator>
  </RadixRadioGroup.Item>
));
RadioGroupItem.displayName = "RadioGroupItem";
