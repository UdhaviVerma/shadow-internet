import type { NextConfig } from "next";
import path from "node:path";

const config: NextConfig = {
  poweredByHeader: false,
  output: "standalone",
  outputFileTracingRoot: path.resolve(process.cwd()),
  async rewrites() {
    const origin = process.env.API_BASE_URL ?? "http://127.0.0.1:8001";
    if (!/^https?:\/\//.test(origin)) throw new Error("API_BASE_URL must be an HTTP(S) backend origin");
    return [{ source: "/api/:path*", destination: `${origin.replace(/\/$/, "")}/api/:path*` }];
  },
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Frame-Options", value: "DENY" },
      ],
    }];
  },
};
export default config;
