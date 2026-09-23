import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  const isProduction = process.env.NEXT_PUBLIC_ENVIRONMENT === "production";
  return {
    rules: isProduction
      ? {
          userAgent: "*",
          allow: "/",
          disallow: ["/app", "/api", "/dev"],
        }
      : {
          userAgent: "*",
          disallow: "/",
        },
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
