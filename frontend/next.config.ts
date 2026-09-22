import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
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
