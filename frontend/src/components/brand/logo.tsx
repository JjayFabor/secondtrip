import { cn } from "@/lib/utils";

/**
 * Logo — the open-loop S mark, shipped. See
 * docs/architecture/22-design-system.md §7.
 *
 * Recolored to the app's own UI palette: Deep Petrol (#12343B) for the
 * mark's dark ground, Primary Teal (#0B7A75) for the accent stroke/dot.
 * The `dark` lockup's "Trip" text uses a lighter tint of teal (#6DAFAC —
 * color-mix(teal 60%, white 40%), the same derivation tokens.css uses for
 * hover/tint shades) for contrast against its own petrol card. The mark
 * originally shipped with independent navy/indigo brand colors (see
 * PLAN.md D37); this recolor (D38) unifies it with the rest of the
 * product instead of keeping the two palettes deliberately separate.
 */
export type LogoVariant = "horizontal" | "icon" | "mono" | "dark";

export interface LogoProps {
  variant?: LogoVariant;
  className?: string;
}

export function Logo({ variant = "horizontal", className }: LogoProps) {
  switch (variant) {
    case "icon":
      return <IconMark className={cn("h-8 w-8", className)} />;
    case "dark":
      // Self-contained lockup — it paints its own dark card, so it can
      // sit on any background without an extra wrapper.
      return <DarkLockup className={cn("h-10 w-auto", className)} />;
    case "mono":
      return <MonochromeLockup className={cn("h-8 w-auto", className)} />;
    case "horizontal":
    default:
      return <PrimaryLockup className={cn("h-8 w-auto", className)} />;
  }
}

function IconMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 180 180"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="SecondTrip"
    >
      <rect width="180" height="180" rx="42" fill="#12343B" />
      <circle cx="48" cy="56" r="8" fill="#0B7A75" />
      <path
        d="M48 56H112C126 56 134 64 134 76C134 88 126 96 112 96H72C58 96 50 104 50 116C50 128 58 136 72 136H122"
        stroke="white"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 122L136 136L120 150"
        stroke="#0B7A75"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PrimaryLockup({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 720 180"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="SecondTrip"
    >
      <rect width="180" height="180" rx="42" fill="#12343B" />
      <circle cx="48" cy="56" r="8" fill="#0B7A75" />
      <path
        d="M48 56H112C126 56 134 64 134 76C134 88 126 96 112 96H72C58 96 50 104 50 116C50 128 58 136 72 136H122"
        stroke="white"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 122L136 136L120 150"
        stroke="#0B7A75"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <text
        x="220"
        y="112"
        fill="#12343B"
        fontFamily="var(--font-sans), Arial, sans-serif"
        fontSize="72"
        fontWeight="700"
        letterSpacing="-2.2"
      >
        Second<tspan fill="#0B7A75">Trip</tspan>
      </text>
    </svg>
  );
}

function DarkLockup({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 720 180"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="SecondTrip"
    >
      <rect width="720" height="180" rx="28" fill="#12343B" />
      <rect x="18" y="18" width="144" height="144" rx="34" fill="white" />
      <circle cx="56" cy="63" r="7" fill="#0B7A75" />
      <path
        d="M56 63H108C120 63 128 70 128 81C128 92 120 99 108 99H76C64 99 57 106 57 117C57 128 64 135 76 135H116"
        stroke="#12343B"
        strokeWidth="12"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M115 123L128 135L115 147"
        stroke="#0B7A75"
        strokeWidth="12"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <text
        x="198"
        y="112"
        fill="white"
        fontFamily="var(--font-sans), Arial, sans-serif"
        fontSize="72"
        fontWeight="700"
        letterSpacing="-2.2"
      >
        Second<tspan fill="#6DAFAC">Trip</tspan>
      </text>
    </svg>
  );
}

function MonochromeLockup({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 720 180"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="SecondTrip"
    >
      <rect width="180" height="180" rx="42" fill="#12343B" />
      <circle cx="48" cy="56" r="8" fill="white" />
      <path
        d="M48 56H112C126 56 134 64 134 76C134 88 126 96 112 96H72C58 96 50 104 50 116C50 128 58 136 72 136H122"
        stroke="white"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 122L136 136L120 150"
        stroke="white"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <text
        x="220"
        y="112"
        fill="#12343B"
        fontFamily="var(--font-sans), Arial, sans-serif"
        fontSize="72"
        fontWeight="700"
        letterSpacing="-2.2"
      >
        SecondTrip
      </text>
    </svg>
  );
}
