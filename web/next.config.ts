import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/runs/:path*",
        destination:
          (process.env.DEMODAY_API_URL || "http://127.0.0.1:8000") +
          "/api/runs/:path*",
      },
    ];
  },
  experimental: { proxyTimeout: 180_000 },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
