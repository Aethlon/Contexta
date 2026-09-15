"use client";

import React, { useState } from "react";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signInAction } from "@/app/actions";

export function SignInForm() {
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);

  return (
    <form
      action={async (formData) => {
        setPending(true);
        try {
          await signInAction(formData);
        } finally {
          setPending(false);
        }
      }}
      className="space-y-5"
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" placeholder="you@company.com" type="email" required />
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">Password</Label>
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="flex items-center gap-1 text-[11px] text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors focus:outline-none"
          >
            {showPassword ? (
              <>
                <EyeOff className="h-3.5 w-3.5" />
                <span>Hide</span>
              </>
            ) : (
              <>
                <Eye className="h-3.5 w-3.5" />
                <span>Show</span>
              </>
            )}
          </button>
        </div>
        <div className="relative">
          <Input
            id="password"
            name="password"
            placeholder="At least 8 characters"
            type={showPassword ? "text" : "password"}
            required
          />
        </div>
      </div>

      <Button className="w-full mt-2" type="submit" disabled={pending}>
        {pending ? (
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-1" />
        ) : null}
        Continue <ArrowRight className="h-4 w-4" strokeWidth={1.2} />
      </Button>
    </form>
  );
}
