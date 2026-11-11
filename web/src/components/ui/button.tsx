"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold leading-tight tracking-tight transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus active:opacity-90 disabled:cursor-not-allowed disabled:opacity-[0.45]",
  {
    variants: {
      variant: {
        primary:
          "border-mt-accent bg-mt-accent text-mt-accent-fg hover:border-mt-accent-hover hover:bg-mt-accent-hover",
        secondary:
          "border-mt-border-strong bg-transparent text-mt-fg hover:border-mt-accent hover:text-mt-accent-hover",
        danger:
          "border-mt-danger-border bg-transparent text-mt-danger hover:bg-mt-danger-bg",
        ghost: "border-transparent bg-transparent px-2 text-mt-muted hover:text-mt-fg",
        // Filter chips. The pressed state is visible (border + accent text),
        // not only announced (TASK-35).
        toggle:
          "border-mt-border-strong bg-transparent px-2 py-1 text-xs text-mt-muted hover:border-mt-accent hover:text-mt-fg aria-pressed:border-mt-accent aria-pressed:bg-mt-accent-soft aria-pressed:text-mt-accent-hover",
      },
    },
    defaultVariants: {
      variant: "primary",
    },
  },
);

function Button({
  className,
  variant,
  asChild = false,
  type = "button",
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const classNameValue = cn(buttonVariants({ variant }), className);
  if (asChild) {
    return <Slot className={classNameValue} {...props} />;
  }
  return <button className={classNameValue} type={type} {...props} />;
}

export { Button, buttonVariants };
