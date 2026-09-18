import * as React from "react";
import { Popover as RadixPopover } from "radix-ui";

import { cn } from "@/lib/utils";

export const Popover = RadixPopover.Root;
export const PopoverTrigger = RadixPopover.Trigger;
export const PopoverAnchor = RadixPopover.Anchor;

export const PopoverContent = React.forwardRef<
  React.ElementRef<typeof RadixPopover.Content>,
  React.ComponentPropsWithoutRef<typeof RadixPopover.Content>
>(({ className, align = "center", sideOffset = 6, ...props }, ref) => (
  <RadixPopover.Portal>
    <RadixPopover.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        "z-50 w-72 rounded-[var(--radius-card)] border border-border-subtle bg-surface-raised p-4",
        "shadow-sm",
        className,
      )}
      {...props}
    />
  </RadixPopover.Portal>
));
PopoverContent.displayName = "PopoverContent";
