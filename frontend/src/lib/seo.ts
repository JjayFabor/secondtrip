import type { Metadata } from "next";

const SITE_NAME = "SecondTrip";
const DEFAULT_LOCAL_URL = "http://localhost:3000";

export interface SeoPage {
  title: string;
  description: string;
  path: string;
}

export interface FaqEntry {
  question: string;
  answer: string;
}

type JsonLdNode = Record<string, unknown>;

export function getSiteUrl(): URL {
  const configured = process.env.NEXT_PUBLIC_APP_URL;
  if (configured) return new URL(configured);

  if (process.env.NEXT_PUBLIC_ENVIRONMENT === "production") {
    throw new Error("NEXT_PUBLIC_APP_URL is required in production.");
  }
  return new URL(DEFAULT_LOCAL_URL);
}

export function absoluteUrl(path: string): string {
  return new URL(path, getSiteUrl()).toString();
}

export function pageMetadata({ title, description, path }: SeoPage): Metadata {
  const canonical = absoluteUrl(path);
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      type: "website",
      siteName: SITE_NAME,
      title,
      description,
      url: canonical,
      images: [{ url: absoluteUrl("/opengraph-image"), width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [absoluteUrl("/opengraph-image")],
    },
  };
}

export function organizationJsonLd(): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: absoluteUrl("/"),
    logo: absoluteUrl("/icon.svg"),
  };
}

export function websiteJsonLd(): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: absoluteUrl("/"),
    description:
      "Callback and rework analytics for service businesses using their existing job history.",
  };
}

export function softwareApplicationJsonLd(): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE_NAME,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description:
      "Import service-job history, surface possible repeat visits, inspect the evidence, and record a human decision.",
    url: absoluteUrl("/features"),
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      description: "Free private beta",
    },
  };
}

export function faqJsonLd(entries: readonly FaqEntry[]): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: entries.map((entry) => ({
      "@type": "Question",
      name: entry.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: entry.answer,
      },
    })),
  };
}

export function breadcrumbJsonLd(
  items: readonly { name: string; path: string }[],
): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}
