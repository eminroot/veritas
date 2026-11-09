import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/*
 * The console's button vocabulary on shadcn's API: dark acts, lime marks,
 * r12, regular weight. Default and secondary carry the lime sweep the
 * console's `.btn` has (a ::before panel scaling from the left, behind the
 * label — `isolate` plus `-z-10` keeps it there without wrapping the text).
 */
const SWEEP =
  "relative isolate overflow-hidden before:absolute before:inset-[3px] before:-z-10 before:rounded-[9px] before:bg-lime before:origin-left before:scale-x-0 before:transition-transform before:duration-500 before:[transition-timing-function:cubic-bezier(0.16,1,0.3,1)] hover:before:scale-x-100"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-normal tracking-[-0.01em] ring-offset-background transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.985] [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: `bg-primary text-primary-foreground hover:text-ink ${SWEEP}`,
        destructive:
          "bg-stop/10 text-stop hover:bg-stop/20",
        outline:
          `border border-ink/[0.12] bg-canvas text-ink/75 hover:border-ink/25 hover:text-ink ${SWEEP} before:bg-pg`,
        secondary:
          `bg-pg text-ink/75 hover:text-ink ${SWEEP} before:bg-pg-deep`,
        ghost: "text-ink/75 hover:bg-pg hover:text-ink",
        link: "text-ink underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-[10px] px-3 text-[13px]",
        lg: "h-12 rounded-2xl px-7 text-[15px]",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
