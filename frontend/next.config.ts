import type { NextConfig } from "next";

const isDevelopment = process.env.NODE_ENV === "development";

const configuredApiOrigin = (() => {
  const value = process.env.NEXT_PUBLIC_API_URL;
  if (!value) return null;

  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
})();

const connectSources = [
  "'self'",
  ...(configuredApiOrigin ? [configuredApiOrigin] : []),
  "https://*.r2.cloudflarestorage.com",
  ...(isDevelopment ? ["ws:"] : []),
];

// Static marketing pages cannot use per-request nonces without giving up CDN
// caching. Keep the policy compatible with Next.js hydration and the small
// number of intentional inline styles while restricting every external origin.
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  `connect-src ${connectSources.join(" ")}`,
  "font-src 'self'",
  "form-action 'self'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "img-src 'self' blob: data:",
  "object-src 'none'",
  `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  ...(!isDevelopment ? ["upgrade-insecure-requests"] : []),
].join("; ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          {
            key: "Permissions-Policy",
            value: "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
          },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          ...(!isDevelopment
            ? [
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=31536000; includeSubDomains",
                },
              ]
            : []),
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
  async rewrites() {
    const apiOrigin = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(
      /\/$/,
      "",
    );

    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
