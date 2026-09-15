import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Contexta — Memory Intelligence Layer for AI Agents",
  description:
    "Autonomous memory intelligence, entity graph synthesis, and sub-180ms hybrid vector retrieval for agentic systems.",
};

import { TitleBar } from "@/components/title-bar";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${jetbrainsMono.variable}`}
      data-scroll-behavior="smooth"
      suppressHydrationWarning
    >
      <body
        className="font-sans antialiased text-[var(--foreground)] bg-[var(--background)] selection:bg-[#27272a] selection:text-[#e4e4e7]"
        suppressHydrationWarning
      >
        <div className="relative z-10 min-h-screen flex flex-col font-sans">
          <TitleBar />
          <Providers>{children}</Providers>
        </div>
      </body>
    </html>
  );
}
