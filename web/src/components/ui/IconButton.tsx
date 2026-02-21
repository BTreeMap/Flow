import type { ButtonHTMLAttributes, ReactNode } from "react";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  label: string;
}

export function IconButton({
  children,
  label,
  className = "",
  ...props
}: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={`inline-flex items-center justify-center w-[var(--tap)] h-[var(--tap)] rounded-full hover:bg-surface-2 active:bg-surface-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 disabled:pointer-events-none ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
