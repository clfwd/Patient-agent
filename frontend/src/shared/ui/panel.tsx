import type { HTMLAttributes, PropsWithChildren } from "react";

import { cn } from "@/shared/lib/cn";

export function Panel({ children, className, ...props }: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) {
  return (
    <div className={cn("glass-panel", className)} {...props}>
      {children}
    </div>
  );
}
