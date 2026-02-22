import { Link, useLocation } from "react-router";
import { MessageCircle, Bell, Settings, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useAuth } from "../../auth";

interface NavRailItem {
  to: string;
  icon: ReactNode;
  label: string;
  testId: string;
  match?: string[];
  adminOnly?: boolean;
}

const navItems: NavRailItem[] = [
  {
    to: "/dashboard",
    icon: <MessageCircle className="w-5 h-5" />,
    label: "Chats",
    testId: "nav-chats",
    match: ["/dashboard", "/p/"],
  },
  {
    to: "/updates",
    icon: <Bell className="w-5 h-5" />,
    label: "Updates",
    testId: "nav-updates",
    match: ["/updates"],
  },
  {
    to: "/settings",
    icon: <Settings className="w-5 h-5" />,
    label: "Settings",
    testId: "nav-settings",
    match: ["/settings"],
  },
  {
    to: "/admin",
    icon: <ShieldCheck className="w-5 h-5" />,
    label: "Admin",
    testId: "nav-admin",
    match: ["/admin"],
    adminOnly: true,
  },
];

function isActive(item: NavRailItem, pathname: string): boolean {
  return (item.match ?? [item.to]).some((m) => pathname.startsWith(m));
}

export function NavRail() {
  const { pathname } = useLocation();
  const { role } = useAuth();

  return (
    <nav
      aria-label="Main navigation"
      data-testid="nav-rail"
      className="flex flex-col items-center gap-1 w-[72px] min-h-0 h-full bg-surface border-r border-divider pt-4 pb-[env(safe-area-inset-bottom,0px)]"
    >
      {navItems
        .filter((item) => !item.adminOnly || role === "admin")
        .map((item) => {
          const active = isActive(item, pathname);
          return (
            <Link
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              title={item.label}
              className={`flex flex-col items-center justify-center gap-0.5 w-14 h-14 rounded-[var(--radius-md)] text-[11px] transition-colors ${
                active
                  ? "text-primary bg-primary/10 font-medium"
                  : "text-text-muted hover:bg-surface-2"
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
            </Link>
          );
        })}
    </nav>
  );
}
