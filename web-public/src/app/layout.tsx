import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Contexta | The Memory Intelligence Layer for AI Agents",
  description: "Contexta Cloud gives AI agents persistent, long-term memory with truth maintenance, sensitive-data redaction, and explainable retrieval. BYOK. Sub-100ms p99. Or self-host.",
  keywords: [
    "Agent Memory Cloud",
    "Managed AI Memory",
    "Memory Layer for Agents",
    "BYOK AI Memory",
    "AI Agent Memory",
    "Long-Term AI Memory",
    "Context Window Optimization",
    "AI Memory Pipeline",
    "Tenant Isolation AI",
    "Dream Cycle memory"
  ],
  authors: [{ name: "Contexta Team", url: "https://contexta.dev" }],
  openGraph: {
    title: "Contexta | The Memory Intelligence Layer for AI Agents",
    description: "Contexta Cloud gives AI agents persistent, long-term memory with truth maintenance, sensitive-data redaction, and explainable retrieval. BYOK. Sub-100ms p99. Or self-host.",
    url: "https://contexta.dev",
    siteName: "Contexta",
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Contexta | The Memory Intelligence Layer for AI Agents",
    description: "Contexta Cloud gives AI agents persistent, long-term memory with truth maintenance, sensitive-data redaction, and explainable retrieval. BYOK. Sub-100ms p99.",
  },
  robots: {
    index: true,
    follow: true,
  }
};

// Rich snippet Structured Data (JSON-LD) for Search Engines
const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Contexta",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "All",
  "description": "Contexta Cloud gives AI agents persistent, long-term memory with truth maintenance, sensitive-data redaction, and explainable retrieval. BYOK. Sub-100ms p99. Or self-host.",
  "license": "https://opensource.org/licenses/Apache-2.0",
  "softwareVersion": "0.1.0",
  "offers": [
    {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD",
      "category": "OpenSource"
    },
    {
      "@type": "Offer",
      "price": "19",
      "priceCurrency": "USD",
      "category": "SaaS"
    }
  ]
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="light">
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="bg-background font-sans font-light text-foreground antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:font-normal focus:text-foreground focus:shadow-[var(--shadow-card)] focus:ring-3 focus:ring-ring/50"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
