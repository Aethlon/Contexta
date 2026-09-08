import path from "node:path";
import type { NextConfig } from "next";

// @aethlon/components is a file: dependency linked outside this project's
// folder. Turbopack only resolves modules inside its root, so root must be
// the common parent of web-public and the linked library repo
// (Aethlon_polyrepo). See nextjs docs: turbopack > root directory.
const monoRoot = path.join(__dirname, "..", "..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: monoRoot,
  turbopack: {
    root: monoRoot,
  },
};

export default nextConfig;
