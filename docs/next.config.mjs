import createMDX from "@next/mdx";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

const withMDX = createMDX({
  extension: /\.mdx?$/,
  options: {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [
      [
        rehypeHighlight,
        {
          // An unregistered language makes rehype-highlight throw, which fails
          // the whole build over a single code fence. Render these as plain
          // text instead so documentation can never break the site.
          plainText: [
            "powershell",
            "ps1",
            "psm1",
            "env",
            "toml",
            "ini",
            "diff",
            "console",
            "output",
            "text",
            "plaintext",
            "shellsession",
            "sql",
            "graphql",
            "yaml",
          ],
        },
      ],
    ],
  },
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  pageExtensions: ["ts", "tsx", "md", "mdx"],
  reactStrictMode: true,
};

export default withMDX(nextConfig);
