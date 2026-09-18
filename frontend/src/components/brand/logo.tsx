import { cn } from "@/lib/utils";

/**
 * Logo — the open-loop S mark, shipped. See
 * docs/architecture/22-design-system.md §7.
 *
 * The mark carries its own fixed brand colors (navy #0B1220, indigo
 * #4F46E5/#818CF8) rather than the app's teal/apricot token palette —
 * a logotype legitimately has its own brand colors independent of UI
 * accent colors, the same way a wordmark's ink doesn't change with a
 * product's theme. See 22 §7's note on this deliberately NOT being wired
 * through tokens.css.
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
      <rect width="180" height="180" rx="42" fill="#0B1220" />
      <circle cx="48" cy="56" r="8" fill="#4F46E5" />
      <path
        d="M48 56H112C126 56 134 64 134 76C134 88 126 96 112 96H72C58 96 50 104 50 116C50 128 58 136 72 136H122"
        stroke="white"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 122L136 136L120 150"
        stroke="#4F46E5"
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
      <rect width="180" height="180" rx="42" fill="#0B1220" />
      <circle cx="48" cy="56" r="8" fill="#4F46E5" />
      <path
        d="M48 56H112C126 56 134 64 134 76C134 88 126 96 112 96H72C58 96 50 104 50 116C50 128 58 136 72 136H122"
        stroke="white"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M120 122L136 136L120 150"
        stroke="#4F46E5"
        strokeWidth="14"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <text
        x="220"
        y="112"
        fill="#0B1220"
        fontFamily="var(--font-sans), Arial, sans-serif"
        fontSize="72"
        fontWeight="700"
        letterSpacing="-2.2"
      >
        Second<tspan fill="#4F46E5">Trip</tspan>
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
      <rect width="720" height="180" rx="28" fill="#0B1220" />
      <rect x="18" y="18" width="144" height="144" rx="34" fill="white" />
      <circle cx="56" cy="63" r="7" fill="#4F46E5" />
      <path
        d="M56 63H108C120 63 128 70 128 81C128 92 120 99 108 99H76C64 99 57 106 57 117C57 128 64 135 76 135H116"
        stroke="#0B1220"
        strokeWidth="12"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M115 123L128 135L115 147"
        stroke="#4F46E5"
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
        Second<tspan fill="#818CF8">Trip</tspan>
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
      <rect width="180" height="180" rx="42" fill="#0B1220" />
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
        fill="#0B1220"
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
