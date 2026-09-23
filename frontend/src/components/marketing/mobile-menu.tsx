"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface MarketingNavLink {
  label: string;
  href: string;
}

export function MobileMenu({ links }: { links: readonly MarketingNavLink[] }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLAnchorElement>("a")?.focus();

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  return (
    <div className="md:hidden">
      <Button
        ref={triggerRef}
        type="button"
        variant="ghost"
        size="icon"
        aria-label={open ? "Close navigation" : "Open navigation"}
        aria-expanded={open}
        aria-controls="mobile-navigation"
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
      </Button>
      {open ? (
        <div
          ref={panelRef}
          id="mobile-navigation"
          className="absolute inset-x-0 top-full z-50 border-b border-border-strong bg-surface-raised px-6 py-5 shadow-sm"
        >
          <nav aria-label="Mobile navigation" className="mx-auto flex max-w-6xl flex-col gap-1">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="rounded-[var(--radius-control)] px-3 py-3 text-base font-medium text-text-primary hover:bg-surface-canvas"
                onClick={() => setOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border-subtle pt-4">
              <Button asChild variant="secondary">
                <Link href="/login" onClick={() => setOpen(false)}>Sign In</Link>
              </Button>
              <Button asChild>
                <Link href="/register" onClick={() => setOpen(false)}>Try SecondTrip</Link>
              </Button>
            </div>
          </nav>
        </div>
      ) : null}
    </div>
  );
}
