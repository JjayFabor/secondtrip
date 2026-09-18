import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Table — tables are first-class in this product
 * (docs/architecture/22-design-system.md §14; 20-frontend-and-seo.md §7).
 * `TableHead`/`TableCell` accept `align="right"` and apply tabular-nums
 * automatically for numeric columns — consistent alignment is what makes a
 * column of money or counts trustworthy at a glance.
 */
export function Table({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn("sticky top-0 z-10 border-b border-border-subtle bg-surface-raised", className)}
      {...props}
    />
  );
}

export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TableFooter({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tfoot
      className={cn("border-t border-border-subtle bg-surface-canvas font-medium", className)}
      {...props}
    />
  );
}

export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-border-subtle transition-colors duration-[var(--duration-fast)]",
        "hover:bg-surface-canvas",
        className,
      )}
      {...props}
    />
  );
}

interface AlignProp {
  /** Right-align and apply tabular-nums — use for money, counts, percentages. */
  align?: "left" | "right";
}

export function TableHead({
  className,
  align = "left",
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement> & AlignProp) {
  return (
    <th
      className={cn(
        "h-10 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide",
        "text-text-secondary [&:has([role=checkbox])]:pr-0",
        align === "right" && "text-right tabular-nums",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({
  className,
  align = "left",
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement> & AlignProp) {
  return (
    <td
      className={cn(
        "px-4 py-3 align-middle text-text-primary [&:has([role=checkbox])]:pr-0",
        align === "right" && "text-right tabular-nums",
        className,
      )}
      {...props}
    />
  );
}

export function TableCaption({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableCaptionElement>) {
  return <caption className={cn("mt-4 text-sm text-text-secondary", className)} {...props} />;
}
