import Link from "next/link";

import { Logo } from "@/components/brand/logo";

const GROUPS = [
  {
    title: "Product",
    links: [
      { label: "Overview", href: "/features" },
      { label: "How it works", href: "/#how-it-works" },
      { label: "Pricing", href: "/pricing" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Contact", href: "/contact" },
      { label: "Sign in", href: "/login" },
      { label: "Create workspace", href: "/register" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy", href: "/privacy" },
      { label: "Terms", href: "/terms" },
      { label: "Subprocessors", href: "/subprocessors" },
      { label: "DPA requests", href: "/dpa" },
    ],
  },
] as const;

export function Footer() {
  return (
    <footer className="border-t border-border-subtle bg-surface-raised">
      <div className="mx-auto grid max-w-6xl gap-10 px-6 py-12 sm:grid-cols-[1.2fr_2fr]">
        <div>
          <Link href="/" className="inline-flex" aria-label="SecondTrip home">
            <Logo variant="horizontal" />
          </Link>
          <p className="mt-4 max-w-xs text-sm leading-6 text-text-secondary">
            Explainable callback and rework analytics for service teams.
          </p>
          <p className="mt-6 text-sm text-text-secondary">Built by Jjay Fabor</p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3">
          {GROUPS.map((group) => (
            <div key={group.title}>
              <h2 className="text-sm font-semibold text-text-primary">{group.title}</h2>
              <ul className="mt-4 space-y-3">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-text-secondary transition-colors duration-[var(--duration-fast)] hover:text-text-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>
    </footer>
  );
}
