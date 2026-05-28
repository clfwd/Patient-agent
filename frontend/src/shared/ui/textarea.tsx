import type { TextareaHTMLAttributes } from "react";

import { cn } from "@/shared/lib/cn";

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-[120px] w-full resize-none rounded-[24px] border border-line bg-transparent px-4 py-4 text-[15px] text-foreground outline-none placeholder:text-muted focus:border-foreground/20",
        props.className,
      )}
    />
  );
}
