import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/seo";

const PUBLIC_PATHS = [
  "/",
  "/features",
  "/pricing",
  "/contact",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return PUBLIC_PATHS.map((path) => ({
    url: absoluteUrl(path),
    changeFrequency: path === "/" ? "weekly" : "monthly",
    priority: path === "/" ? 1 : 0.7,
  }));
}
