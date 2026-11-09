
import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-xl border border-ink/[0.12] bg-canvas px-3.5 py-2 text-base text-ink transition-[border-color,box-shadow] duration-200 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-ink/50 hover:border-ink/25 focus-visible:outline-none focus-visible:border-ink focus-visible:shadow-[0_0_0_3px_rgba(36,36,38,0.07)] disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          // Ensure proper text size and touch targets for mobile
          "touch-manipulation",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
