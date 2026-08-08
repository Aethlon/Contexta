import type { Metadata } from "next";
import { DM_Sans, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
  variable: "--font-dm-sans",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

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
    <html lang="en" className={`${dmSans.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var saved = localStorage.getItem('theme');
                  var darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
                  if (saved === 'dark' || (!saved && darkQuery.matches)) {
                    document.documentElement.classList.add('dark');
                  } else {
                    document.documentElement.classList.remove('dark');
                  }
                } catch (e) {}
              })();
            `
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="font-sans font-light antialiased text-[var(--color-ghost)] bg-[var(--color-abyss)] transition-colors duration-200">
        {/* Subtle noise overlay */}
        <div
          className="fixed inset-0 opacity-[0.015] dark:opacity-[0.02] pointer-events-none z-0"
          style={{ backgroundImage: 'url("https://www.transparenttextures.com/patterns/stardust.png")' }}
        />
        {/* Ambient Glow Orbs */}
        <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
          <div className="absolute top-[-10%] right-[-10%] w-[50vw] h-[50vw] rounded-full bg-[var(--color-purple)]/5 dark:bg-[var(--color-purple)]/[0.06] blur-[120px]" />
          <div className="absolute bottom-[-10%] left-[-10%] w-[60vw] h-[60vw] rounded-full bg-blue-500/[0.03] dark:bg-blue-500/[0.04] blur-[140px]" />
          <div className="absolute top-[40%] left-[50%] -translate-x-1/2 w-[40vw] h-[40vw] rounded-full bg-[var(--color-purple)]/[0.02] dark:bg-[var(--color-purple)]/[0.03] blur-[120px]" />
        </div>
        <div className="relative z-10 min-h-screen flex flex-col">
          <Providers>{children}</Providers>
        </div>
      </body>
    </html>
  );
}
