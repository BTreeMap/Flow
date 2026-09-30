import type { ReactNode, MouseEvent } from "react";
import { Badge } from "../Badge";

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
      className={`group flex items-center gap-3 px-3 mx-1 h-[72px] rounded-md hover:bg-surface-2 active:bg-surface-3 transition-colors duration-150 cursor-pointer ${className}`}
    >
      {avatar && <div className="shrink-0">{avatar}</div>}
      <div className="flex-1 min-w-0">
        <p className={`text-[15px] truncate ${unread ? "font-semibold text-text" : "font-medium text-text"}`}>{primary}</p>
        {secondary && (
          <p className={`text-[13px] truncate leading-tight mt-0.5 ${unread ? "text-text-muted" : "text-text-subtle"}`}>
            {secondary}
          </p>
        )}
      </div>
      <div className="shrink-0 flex flex-col items-end gap-1.5">
        {trailing}
        {unread && <Badge dot tone="primary" />}
      </div>
    </div>
  );
}
