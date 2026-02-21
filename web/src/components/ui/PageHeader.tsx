import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  actions?: ReactNode;
  "data-testid"?: string;
}

export function PageHeader({ title, actions, "data-testid": testId }: PageHeaderProps) {
  return (
    <header className="sticky top-0 z-40 flex items-center justify-between h-[var(--header-h)] px-4 bg-surface/95 backdrop-blur-sm border-b border-divider" data-testid={testId}>
      <h1 className="text-[17px] font-semibold text-text">{title}</h1>
      {actions && <div className="flex items-center gap-1">{actions}</div>}
    </header>
  );
}
