import type { ReactNode, MouseEvent } from "react";

interface ListRowProps {
  avatar?: ReactNode;
  primary: string;
  secondary?: string;
  trailing?: ReactNode;
  unread?: boolean;
  onClick?: (e: MouseEvent) => void;
  className?: string;
}

export function ListRow({
  avatar,
  primary,
  secondary,
  trailing,
  unread,
  onClick,
  className = "",
}: ListRowProps) {
  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick(e as unknown as MouseEvent);
              }
            }
          : undefined
      }
      className={`flex items-center gap-3 px-4 h-[72px] hover:bg-surface-2 active:bg-surface-3 transition-colors cursor-pointer ${className}`}
    >
      {avatar && <div className="shrink-0">{avatar}</div>}
      <div className="flex-1 min-w-0">
        <p className="text-[16px] font-medium text-text truncate">{primary}</p>
        {secondary && (
          <p className="text-[13px] text-text-muted truncate leading-tight">
            {secondary}
          </p>
        )}
      </div>
      <div className="shrink-0 flex flex-col items-end gap-1">
        {trailing}
        {unread && (
          <span className="w-2 h-2 rounded-full bg-primary" />
        )}
      </div>
    </div>
  );
}
