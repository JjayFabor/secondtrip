import * as React from "react";
import { Separator as RadixSeparator } from "radix-ui";

import { cn } from "@/lib/utils";

/** Decorative divider only — uses --border-subtle, never --border-strong. */
export const Separator = React.forwardRef<
  React.ElementRef<typeof RadixSeparator.Root>,
  React.ComponentPropsWithoutRef<typeof RadixSeparator.Root>
>(({ className, orientation = "horizontal", decorative = true, ...props }, ref) => (
  <RadixSeparator.Root
    ref={ref}
    orientation={orientation}
    decorative={decorative}
    className={cn(
      "bg-border-subtle",
      orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
      className,
    )}
    {...props}
  />
));
Separator.displayName = "Separator";
