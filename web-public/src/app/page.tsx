import { MotionConfig } from "motion/react";
import { Navbar } from "@/components/layout/navbar";
import { Hero } from "@/components/sections/hero";
import { Stats } from "@/components/sections/stats";
import { Problem } from "@/components/sections/problem";
import { Features } from "@/components/sections/features";
import { Benchmarks } from "@/components/sections/benchmarks";
import { HowItWorks } from "@/components/sections/how-it-works";
import { Integrations } from "@/components/sections/integrations";
import { Security } from "@/components/sections/security";
import { Pricing } from "@/components/sections/pricing";
import { FAQ } from "@/components/sections/faq";
import { CTA } from "@/components/sections/cta";
import { Footer } from "@/components/sections/footer";

export default function Home() {
  return (
    <MotionConfig reducedMotion="user">
      <Navbar />
      <main id="main" className="flex-1">
        <Hero />
        <Stats />
        <Problem />
        <Features />
        <Benchmarks />
        <HowItWorks />
        <Integrations />
        <Security />
        <Pricing />
        <FAQ />
        <CTA />
      </main>
      <Footer />
    </MotionConfig>
  );
}
