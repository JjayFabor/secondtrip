import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, resolving conflicting Tailwind utilities (e.g. two
 * different `bg-*` classes) in favor of the one that appears last.
 * Every primitive in components/ui uses this instead of string
 * concatenation, so a consumer's `className` prop can safely override
 * a default.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
