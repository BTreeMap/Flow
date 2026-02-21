import { Link, useLocation } from "react-router";
import { MessageCircle, Bell, Settings } from "lucide-react";
import type { ReactNode } from "react";

interface NavItem {
  to: string;
  icon: ReactNode;
  label: string;
  match?: string[];
}

const navItems: NavItem[] = [
  {
    to: "/dashboard",
    icon: <MessageCircle className="w-5 h-5" />,
    label: "Chats",
    match: ["/dashboard", "/p/"],
  },
  {
    to: "/updates",
    icon: <Bell className="w-5 h-5" />,
    label: "Updates",
    match: ["/updates"],
  },
  {
    to: "/settings",
    icon: <Settings className="w-5 h-5" />,
    label: "Settings",
    match: ["/settings"],
  },
];

function isActive(item: NavItem, pathname: string): boolean {
  return (item.match ?? [item.to]).some((m) => pathname.startsWith(m));
}

export function BottomNav() {
  const { pathname } = useLocation();

  return (
    <nav className="fixed bottom-0 inset-x-0 z-50 bg-surface border-t border-divider md:hidden" style={{ height: "calc(var(--bottomnav-h) + env(safe-area-inset-bottom, 0px))", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
      <div className="flex items-center justify-around h-[var(--bottomnav-h)]">
        {navItems.map((item) => {
          const active = isActive(item, pathname);
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`flex flex-col items-center justify-center gap-0.5 min-w-[var(--tap)] h-[var(--tap)] text-[11px] transition-colors ${
                active
                  ? "text-primary font-medium"
                  : "text-text-muted"
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
