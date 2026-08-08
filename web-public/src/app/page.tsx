import React from "react";
import { Navbar } from "@/components/layout/navbar";
import { Hero } from "@/components/sections/hero";
import { Stats } from "@/components/sections/stats";
import { Problem } from "@/components/sections/problem";
import { Features } from "@/components/sections/features";
import { HowItWorks } from "@/components/sections/how-it-works";
import { Integrations } from "@/components/sections/integrations";
import { Security } from "@/components/sections/security";
import { Pricing } from "@/components/sections/pricing";
import { Community } from "@/components/sections/community";
import { FAQ } from "@/components/sections/faq";
import { CTA } from "@/components/sections/cta";
import { Footer } from "@/components/sections/footer";

export default function Home() {
  return (
    <>
      <Navbar />
      <main className="flex-1">
        <Hero />
        <Stats />
        <Problem />
        <Features />
        <HowItWorks />
        <Integrations />
        <Security />
        <Pricing />
        <Community />
        <FAQ />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
