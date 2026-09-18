"use client";

import * as React from "react";

import { Sidebar, type SidebarItem } from "@/components/dashboard/sidebar";
import { TopBar } from "@/components/dashboard/topbar";

/**
 * DashboardLayout — sidebar fixed at 224px on desktop; below 1024px it
 * collapses into a drawer (docs/architecture/22-design-system.md §11, §14).
 * Structure and responsive behavior only — real navigation targets and the
 * session guard arrive in PLAN.md Step 3.
 */
interface DashboardLayoutProps {
  children: React.ReactNode;
  primaryItems?: SidebarItem[];
  secondaryItems?: SidebarItem[];
  activeHref?: string;
  topBarContent?: React.ReactNode;
}

export function DashboardLayout({
  children,
  primaryItems,
  secondaryItems,
  activeHref,
  topBarContent,
}: DashboardLayoutProps) {
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  React.useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  return (
    <div className="flex h-dvh bg-surface-canvas">
      {/* Desktop sidebar — hidden below 1024px */}
      <div className="hidden lg:block">
        <Sidebar
          primaryItems={primaryItems}
          secondaryItems={secondaryItems}
          activeHref={activeHref}
        />
      </div>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-[var(--color-ink)]/40"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="relative h-full w-[224px] shadow-md">
            <Sidebar
              primaryItems={primaryItems}
              secondaryItems={secondaryItems}
              activeHref={activeHref}
              onClose={() => setDrawerOpen(false)}
              className="w-full"
            />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenSidebar={() => setDrawerOpen(true)}>{topBarContent}</TopBar>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
