import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "gold";
  size?: "sm" | "md" | "lg";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-md font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-ring)] disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98]",
          
          // Variants
          variant === "primary" && "bg-[var(--color-primary)] text-[var(--color-primary-foreground)] hover:opacity-90 shadow-sm",
          variant === "secondary" && "bg-[var(--color-secondary)] text-[var(--color-secondary-foreground)] hover:bg-[var(--color-accent)] border border-transparent",
          variant === "outline" && "border border-[var(--color-border)] bg-transparent text-[var(--color-foreground)] hover:bg-[var(--color-charcoal)]",
          variant === "ghost" && "bg-transparent text-[var(--color-foreground)] hover:bg-[var(--color-ash)]",
          variant === "gold" && "bg-[var(--color-purple)] text-[var(--color-abyss)] font-semibold shadow-md shadow-[var(--color-purple)]/10 hover:brightness-110 hover:shadow-[var(--color-purple)]/20",
          
          // Sizes
          size === "sm" && "h-8 px-3 text-xs rounded-sm",
          size === "md" && "h-10 px-4 text-sm rounded-md",
          size === "lg" && "h-12 px-6 text-base rounded-lg",
          
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
