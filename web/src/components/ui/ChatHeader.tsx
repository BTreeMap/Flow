import { useNavigate } from "react-router";
import { ArrowLeft, MoreVertical, Bug } from "lucide-react";
import { IconButton } from "./IconButton";
import { useState, useRef, useEffect } from "react";
import type { ReactNode } from "react";
import { useAuth } from "../../auth";

interface ChatHeaderProps {
  title: string;
  avatar?: ReactNode;
  backTo?: string;
  hideBack?: boolean;
  connectionStatus?: "online" | "reconnecting" | "offline";
  menuItems?: { label: string; onClick: () => void }[];
  debugMode?: boolean;
  onToggleDebug?: () => void;
}

const statusColors = {
  online: "bg-success/20 text-success",
  reconnecting: "bg-warning/20 text-warning",
  offline: "bg-text-subtle/20 text-text-subtle",
};

export function ChatHeader({
  title,
  avatar,
  backTo = "/dashboard",
  hideBack,
  connectionStatus,
  menuItems,
  debugMode,
  onToggleDebug,
}: ChatHeaderProps) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { role } = useAuth();
  const isAdmin = role === "admin";

  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <header className="sticky top-0 z-40 flex items-center gap-2 h-[var(--header-h)] px-2 bg-surface/95 backdrop-blur-sm border-b border-divider">
      {!hideBack && (
        <IconButton label="Back" onClick={() => navigate(backTo)}>
          <ArrowLeft className="w-5 h-5" />
        </IconButton>
      )}
      {hideBack && <div className="w-2" />}

      {avatar && <div className="shrink-0">{avatar}</div>}

      <div className="flex-1 min-w-0">
        <h1 className="text-[17px] font-semibold text-text truncate">
          {title}
        </h1>
        {connectionStatus && (
          <span
            className={`inline-flex items-center text-[11px] px-2 py-0.5 rounded-full ${statusColors[connectionStatus]}`}
          >
            {connectionStatus === "online"
              ? "Online"
              : connectionStatus === "reconnecting"
                ? "Reconnecting…"
                : "Offline"}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1">
        {isAdmin && onToggleDebug && (
          <IconButton
            label="Toggle Debug"
            onClick={onToggleDebug}
            className={debugMode ? "text-primary bg-primary/10" : "text-text-subtle"}
          >
            <Bug className="w-5 h-5" />
          </IconButton>
        )}

        {menuItems && menuItems.length > 0 && (
          <div className="relative" ref={menuRef}>
            <IconButton
              label="Menu"
              onClick={() => setMenuOpen((v) => !v)}
            >
              <MoreVertical className="w-5 h-5" />
            </IconButton>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 bg-surface border border-border rounded-[var(--radius-md)] shadow-md py-1 z-50">
                {menuItems.map((item) => (
                  <button
                    key={item.label}
                    onClick={() => {
                      setMenuOpen(false);
                      item.onClick();
                    }}
                    className="w-full text-left px-4 py-2.5 text-sm text-text hover:bg-surface-2 transition-colors"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
