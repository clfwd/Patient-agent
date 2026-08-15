import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

import { cn } from "@/shared/lib/cn";

type ButtonProps = PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({ children, className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition duration-200",
        variant === "primary" && "bg-foreground text-white hover:bg-black/80",
        variant === "secondary" && "bg-warm text-foreground hover:bg-black/5",
        variant === "ghost" && "bg-transparent text-muted hover:bg-black/5 hover:text-foreground",
        props.disabled && "cursor-not-allowed opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
