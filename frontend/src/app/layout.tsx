import type { Metadata } from "next";
import { Manrope } from "next/font/google";

import { JsonLd } from "@/components/seo/json-ld";
import { getSiteUrl, organizationJsonLd, websiteJsonLd } from "@/lib/seo";
import "@/styles/tokens.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: getSiteUrl(),
  title: {
    default: "SecondTrip — callback and rework analytics",
    template: "%s — SecondTrip",
  },
  description:
    "Import service-job history, surface possible repeat visits, review the evidence, and record the human decision.",
  robots:
    process.env.NEXT_PUBLIC_ENVIRONMENT === "production"
      ? { index: true, follow: true }
      : { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={manrope.variable}>
      <body>
        <JsonLd data={[organizationJsonLd(), websiteJsonLd()]} />
        {children}
      </body>
    </html>
  );
}
