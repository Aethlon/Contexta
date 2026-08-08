import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  experimental: {},
  outputFileTracingRoot: projectDir,
  poweredByHeader: false,
  compress: true,
  productionBrowserSourceMaps: false,
  httpAgentOptions: {
    keepAlive: true,
  },
};

export default nextConfig;
