import React from "react";

export function ContextaMark({
  className = "size-6",
  ...props
}: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      {...props}
    >
      {/* Left Monolith */}
      <path
        d="M 16 30.5
           C 16 27.5 18 25.5 21 23.8
           L 38.5 13.5
           C 41.5 11.8 44 13.2 44 16.5
           L 44 42
           C 44 45 42 48 39.5 50.5
           L 33 57
           C 31 59 30 61.5 30 64.5
           L 30 67
           C 30 70 27.5 71.5 24.5 69.8
           L 18.5 66.2
           C 16.5 65 16 63 16 60.5
           Z"
      />
      {/* Right Monolith (180-deg rotational symmetry) */}
      <path
        d="M 84 69.5
           C 84 72.5 82 74.5 79 76.2
           L 61.5 86.5
           C 58.5 88.2 56 86.8 56 83.5
           L 56 58
           C 56 55 58 52 60.5 49.5
           L 67 43
           C 69 41 70 38.5 70 35.5
           L 70 33
           C 70 30 72.5 28.5 75.5 30.2
           L 81.5 33.8
           C 83.5 35 84 37 84 39.5
           Z"
      />
    </svg>
  );
}

export function ContextaLogo({
  className = "flex items-center gap-2.5",
  markClassName = "size-6",
  textClassName = "font-mono font-normal tracking-tight text-foreground text-base",
}: {
  className?: string;
  markClassName?: string;
  textClassName?: string;
}) {
  return (
    <div className={className}>
      <ContextaMark className={markClassName} />
      <span className={textClassName}>contexta</span>
    </div>
  );
}
