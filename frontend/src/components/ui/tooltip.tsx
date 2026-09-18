import * as React from "react";
import { Tooltip as RadixTooltip } from "radix-ui";

import { cn } from "@/lib/utils";

export const TooltipProvider = RadixTooltip.Provider;
export const Tooltip = RadixTooltip.Root;
export const TooltipTrigger = RadixTooltip.Trigger;

export const TooltipContent = React.forwardRef<
  React.ElementRef<typeof RadixTooltip.Content>,
  React.ComponentPropsWithoutRef<typeof RadixTooltip.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <RadixTooltip.Portal>
    <RadixTooltip.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 overflow-hidden rounded-[6px] bg-brand-deep px-2.5 py-1.5 text-xs text-text-inverse",
        "shadow-sm",
        className,
      )}
      {...props}
    />
  </RadixTooltip.Portal>
));
TooltipContent.displayName = "TooltipContent";
