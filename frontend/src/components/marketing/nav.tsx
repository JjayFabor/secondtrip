import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { MobileMenu } from "@/components/marketing/mobile-menu";
import { Button } from "@/components/ui/button";

/**
 * Marketing nav — docs/architecture/22-design-system.md §10. Simple, no
 * mega menu: logo, four links, sign in, one primary CTA.
 */
const NAV_LINKS = [
  { label: "Product", href: "/features" },
  { label: "How It Works", href: "/#how-it-works" },
  { label: "Pricing", href: "/pricing" },
  { label: "FAQ", href: "/#faq" },
];

export function Nav() {
  return (
    <header className="relative border-b border-border-subtle bg-surface-raised">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-6">
        <Link href="/" className="flex items-center">
          <Logo variant="horizontal" />
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-6 md:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-text-secondary transition-colors duration-[var(--duration-fast)] hover:text-text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Sign In</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/register">Try SecondTrip</Link>
          </Button>
        </div>
        <MobileMenu links={NAV_LINKS} />
      </div>
    </header>
  );
}
