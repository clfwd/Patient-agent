import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";

import { cn } from "@/shared/lib/cn";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(props, ref) {
  return (
    <textarea
      ref={ref}
      {...props}
      className={cn(
        "min-h-[56px] max-h-[208px] w-full resize-none bg-transparent px-1 py-1 text-[15px] leading-7 text-foreground outline-none placeholder:text-muted",
        props.className,
      )}
    />
  );
});
