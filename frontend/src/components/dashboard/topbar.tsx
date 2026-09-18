import { Menu } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * TopBar — optional compact bar above the content area
 * (docs/architecture/22-design-system.md §11). Carries the mobile menu
 * trigger below 1024px and a slot for page-level actions; no icon beside
 * every label, no decoration.
 */
interface TopBarProps {
  onOpenSidebar?: () => void;
  children?: React.ReactNode;
  className?: string;
}

export function TopBar({ onOpenSidebar, children, className }: TopBarProps) {
  return (
    <header
      className={cn(
        "flex h-14 items-center gap-3 border-b border-border-subtle bg-surface-raised px-4",
        className,
      )}
    >
      <button
        type="button"
        onClick={onOpenSidebar}
        aria-label="Open navigation"
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] text-text-secondary",
          "hover:bg-surface-canvas lg:hidden",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
        )}
      >
        <Menu size={20} strokeWidth={1.75} />
      </button>

      <div className="flex flex-1 items-center gap-3">{children}</div>
    </header>
  );
}
