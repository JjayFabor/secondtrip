"use client";

import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import {
  FileWarning,
  FolderInput,
  HelpCircle,
  LayoutGrid,
  LineChart as LineChartIcon,
  Settings,
  UserCircle,
  Wrench,
} from "lucide-react";

import { X } from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

/**
 * Sidebar — docs/architecture/22-design-system.md §11. Text labels with
 * restrained icons, nothing overloaded. Labels follow the product brief's
 * plain language; hrefs are best-guess routes from
 * 16-repository-structure.md and get finalized when real auth-gated
 * routing is built (PLAN.md Step 3) — this component only fixes structure
 * and responsive behavior for now.
 */
export interface SidebarItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

const PRIMARY_ITEMS: SidebarItem[] = [
  { label: "Overview", href: "/app/dashboard", icon: LayoutGrid },
  { label: "Visits", href: "/app/jobs", icon: Wrench },
  { label: "Callbacks", href: "/app/rework", icon: FileWarning },
  { label: "Patterns", href: "/app/analytics", icon: LineChartIcon },
  { label: "Reports", href: "/app/analytics", icon: LineChartIcon },
  { label: "Imports", href: "/app/imports", icon: FolderInput },
];

const SECONDARY_ITEMS: SidebarItem[] = [
  { label: "Settings", href: "/app/settings", icon: Settings },
  { label: "Help", href: "/app/help", icon: HelpCircle },
  { label: "Account", href: "/app/account", icon: UserCircle },
];

interface SidebarProps {
  primaryItems?: SidebarItem[];
  secondaryItems?: SidebarItem[];
  /** The currently active href, for the selected-state treatment. */
  activeHref?: string;
  /** Shows a close button beside the logo — used by the mobile drawer. */
  onClose?: () => void;
  className?: string;
}

export function Sidebar({
  primaryItems = PRIMARY_ITEMS,
  secondaryItems = SECONDARY_ITEMS,
  activeHref,
  onClose,
  className,
}: SidebarProps) {
  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex h-full w-[224px] flex-col gap-1 border-r border-border-subtle bg-surface-raised p-3",
        className,
      )}
    >
      <div className="flex h-10 items-center justify-between px-2">
        <Logo variant="horizontal" />
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)]",
              "text-text-secondary hover:bg-surface-canvas",
            )}
          >
            <X size={18} />
          </button>
        )}
      </div>

      <ul className="mt-2 flex flex-1 flex-col gap-0.5">
        {primaryItems.map((item) => (
          <SidebarLink key={item.label} item={item} active={item.href === activeHref} />
        ))}
      </ul>

      <div className="my-2 h-px bg-border-subtle" />

      <ul className="flex flex-col gap-0.5">
        {secondaryItems.map((item) => (
          <SidebarLink key={item.label} item={item} active={item.href === activeHref} />
        ))}
      </ul>
    </nav>
  );
}

function SidebarLink({ item, active }: { item: SidebarItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-2 text-sm font-medium",
          "transition-colors duration-[var(--duration-fast)]",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]",
          active
            ? "bg-surface-canvas text-text-primary"
            : "text-text-secondary hover:bg-surface-canvas hover:text-text-primary",
        )}
      >
        <Icon size={18} strokeWidth={1.75} />
        {item.label}
      </Link>
    </li>
  );
}
