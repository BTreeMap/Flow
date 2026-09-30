import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}

interface ClickableCardProps extends CardProps {
  onClick?: () => void;
}

const BASE =
  "bg-surface border border-border rounded-lg text-left transition-[background-color,border-color] duration-200 ease-[var(--ease-out)]";

/**
 * Canonical content container.
 *
 * A card with an `onClick` renders as a real `<button>`, not a clickable
 * `<div>`: the interactive form has to be focusable and Enter/Space-activated,
 * and encoding that in the type means no caller can accidentally ship an
 * unreachable card. Depth comes from the hairline border rather than a shadow —
 * the system is colour-block first.
 */
export function Card({
  children,
  className = "",
  onClick,
  "data-testid": testId,
}: ClickableCardProps) {
  if (onClick) {
    return (
      <button
        type="button"
        data-testid={testId}
        className={`${BASE} w-full cursor-pointer hover:bg-surface-2 hover:border-text-subtle outline-none focus-visible:ring-2 focus-visible:ring-focus ${className}`}
        onClick={onClick}
      >
        {children}
      </button>
    );
  }

  return (
    <div data-testid={testId} className={`${BASE} ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "", "data-testid": testId }: CardProps) {
  return (
    <div data-testid={testId} className={`px-6 pt-5 pb-4 border-b border-divider ${className}`}>
      {children}
    </div>
  );
}

export function CardContent({ children, className = "", "data-testid": testId }: CardProps) {
  return (
    <div data-testid={testId} className={`px-6 py-5 ${className}`}>
      {children}
    </div>
  );
}
