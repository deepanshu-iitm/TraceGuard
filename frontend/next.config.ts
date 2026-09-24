import type { NextConfig } from "next";

const backend = process.env.TRACEGUARD_API ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/cases", destination: `${backend}/cases` },
      { source: "/cases/:path*", destination: `${backend}/cases/:path*` },
      { source: "/investigate/:path*", destination: `${backend}/investigate/:path*` },
      { source: "/graph/:path*", destination: `${backend}/graph/:path*` },
      { source: "/monitoring", destination: `${backend}/monitoring` },
      { source: "/monitoring/:path*", destination: `${backend}/monitoring/:path*` },
      { source: "/health", destination: `${backend}/health` },
      { source: "/stats", destination: `${backend}/stats` },
    ];
  },
};

export default nextConfig;
