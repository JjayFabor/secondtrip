import * as React from "react";
import { Accordion as RadixAccordion } from "radix-ui";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

export const Accordion = RadixAccordion.Root;

export const AccordionItem = React.forwardRef<
  React.ElementRef<typeof RadixAccordion.Item>,
  React.ComponentPropsWithoutRef<typeof RadixAccordion.Item>
>(({ className, ...props }, ref) => (
  <RadixAccordion.Item
    ref={ref}
    className={cn("border-b border-border-subtle", className)}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

export const AccordionTrigger = React.forwardRef<
  React.ElementRef<typeof RadixAccordion.Trigger>,
  React.ComponentPropsWithoutRef<typeof RadixAccordion.Trigger>
>(({ className, children, ...props }, ref) => (
  <RadixAccordion.Header className="flex">
    <RadixAccordion.Trigger
      ref={ref}
      className={cn(
        "flex flex-1 items-center justify-between py-4 text-left text-[15px] font-medium",
        "text-text-primary transition-colors duration-[var(--duration-fast)]",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
        "[&[data-state=open]>svg]:rotate-180",
        className,
      )}
      {...props}
    >
      {children}
      <ChevronDown
        size={18}
        className="shrink-0 text-text-secondary transition-transform duration-[var(--duration-base)]"
      />
    </RadixAccordion.Trigger>
  </RadixAccordion.Header>
));
AccordionTrigger.displayName = "AccordionTrigger";

export const AccordionContent = React.forwardRef<
  React.ElementRef<typeof RadixAccordion.Content>,
  React.ComponentPropsWithoutRef<typeof RadixAccordion.Content>
>(({ className, children, ...props }, ref) => (
  <RadixAccordion.Content
    ref={ref}
    className={cn(
      "overflow-hidden text-sm text-text-secondary",
      "data-[state=closed]:animate-[accordion-up_var(--duration-base)_var(--easing-out)]",
      "data-[state=open]:animate-[accordion-down_var(--duration-base)_var(--easing-out)]",
      className,
    )}
    {...props}
  >
    <div className="pb-4 pt-0">{children}</div>
  </RadixAccordion.Content>
));
AccordionContent.displayName = "AccordionContent";
