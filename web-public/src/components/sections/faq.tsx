"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@aethlon/components";
import { motion } from "motion/react";
import { fadeUp, staggerContainer } from "@/lib/motion";
import { faqList } from "@/lib/content";

export function FAQ() {
  return (
    <section id="faq" className="scroll-mt-24 border-t border-border/30">
      <div className="mx-auto max-w-3xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
        >
          <motion.p variants={fadeUp} className="text-micro">
            FAQ
          </motion.p>
          <motion.h2
            variants={fadeUp}
            className="mt-4 text-4xl font-semibold tracking-tight text-foreground"
          >
            Frequently asked{" "}
            <span className="font-emphasis text-aurora">questions</span>
          </motion.h2>
          <motion.div variants={fadeUp} className="mt-10">
            <Accordion defaultValue={[faqList[0].id]}>
              {faqList.map((item) => (
                <AccordionItem key={item.id} value={item.id}>
                  <AccordionTrigger className="text-left font-normal text-foreground">
                    {item.question}
                  </AccordionTrigger>
                  <AccordionContent>
                    <p className="font-light text-sm leading-relaxed text-muted-foreground">
                      {item.answer}
                    </p>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
