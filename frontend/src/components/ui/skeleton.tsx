import { cn } from "@/lib/utils";

/**
 * Skeleton — for layout-shaped loading. For anything that takes real time
 * (an import processing, detection running), show a status sentence
 * instead — see docs/architecture/22-design-system.md §11. No shimmer
 * animation beyond a subtle pulse; never a spinner alone.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-[var(--radius-control)] bg-border-subtle", className)}
      {...props}
    />
  );
}
