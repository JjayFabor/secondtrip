import Link from "next/link";

/**
 * Marketing footer — docs/architecture/22-design-system.md §10. Minimal:
 * Product, Pricing, Privacy, Terms, Contact, plus an optional byline.
 */
const FOOTER_LINKS = [
  { label: "Product", href: "/features" },
  { label: "Pricing", href: "/pricing" },
  { label: "Privacy", href: "/privacy" },
  { label: "Terms", href: "/terms" },
  { label: "Contact", href: "/contact" },
];

export function Footer() {
  return (
    <footer className="border-t border-border-subtle bg-surface-raised">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-6 py-8 text-sm text-text-secondary sm:flex-row sm:justify-between">
        <nav aria-label="Footer" className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="transition-colors duration-[var(--duration-fast)] hover:text-text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <p>Built by Jjay Fabor</p>
      </div>
    </footer>
  );
}
