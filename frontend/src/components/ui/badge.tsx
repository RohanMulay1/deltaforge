import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-mono font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring",
  {
    variants: {
      variant: {
        default: "border-transparent bg-zinc-700 text-zinc-100",
        up: "border-transparent bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
        down: "border-transparent bg-rose-500/20 text-rose-400 border-rose-500/30",
        wolfram: "border-violet-500/40 bg-violet-500/15 text-violet-300",
        cyan: "border-cyan-500/40 bg-cyan-500/15 text-cyan-300",
        outline: "border-zinc-700 text-zinc-300",
        amber: "border-amber-500/40 bg-amber-500/15 text-amber-300",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
