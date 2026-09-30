import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variants = {
  primary:
    "bg-primary text-on-primary shadow-primary hover:bg-primary-hover hover:-translate-y-px hover:shadow-md active:translate-y-0 active:shadow-xs",
  secondary:
    "bg-surface text-text border border-border shadow-xs hover:bg-surface-2 hover:border-text-subtle/40 active:bg-surface-3",
  danger:
    "bg-danger text-on-danger shadow-sm hover:bg-danger-hover hover:-translate-y-px active:translate-y-0",
  ghost: "text-text hover:bg-surface-2 active:bg-surface-3",
};

const sizes = {
  sm: "px-3.5 py-1.5 text-sm gap-1.5",
  md: "px-5 py-2.5 text-sm gap-2",
  lg: "px-6 py-3 text-base gap-2",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center font-medium rounded-pill transition-[transform,background-color,box-shadow,border-color] duration-200 ease-[var(--ease-out)] outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-50 disabled:pointer-events-none disabled:shadow-none ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
