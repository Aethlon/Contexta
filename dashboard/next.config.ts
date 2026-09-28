import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {},
  outputFileTracingRoot: projectDir,
  poweredByHeader: false,
  compress: true,
  productionBrowserSourceMaps: false,
  httpAgentOptions: {
    keepAlive: true,
  },
  // The dev-tools badge renders as a floating circle in the bottom-left corner,
  // which sits directly on top of the tenant switcher in the sidebar footer and
  // makes the organization id unreadable. It is a dev-only affordance, so turn
  // it off rather than moving the layout around it.
  devIndicators: false,
};

export default nextConfig;
