import type { Transition, Variants } from "motion/react";

/*
 * System 02 motion — eased tweens only. No springs anywhere.
 * Local copies typed against the app's `motion` version (the library's
 * re-exported variants are typed against its own nested copy).
 */

export const easeSnappy: Transition = {
  type: "tween",
  ease: [0.4, 0, 0.2, 1],
  duration: 0.2,
};

export const easeSmooth: Transition = {
  type: "tween",
  ease: [0.16, 1, 0.3, 1],
  duration: 0.4,
};

export const easeExit: Transition = {
  type: "tween",
  ease: [0.4, 0, 1, 1],
  duration: 0.25,
};

export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: easeSmooth },
};
