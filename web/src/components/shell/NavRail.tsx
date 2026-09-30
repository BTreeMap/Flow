import { Link, useLocation } from "react-router";
import { useAuth } from "../../auth";
import { NAV_ITEMS, isNavItemActive } from "../../config/nav";

export function NavRail() {
  const { pathname } = useLocation();
  const { role } = useAuth();

  return (
    <nav
      aria-label="Main navigation"
      data-testid="nav-rail"
      className="flex flex-col items-center gap-1 w-[72px] min-h-0 h-full bg-surface border-r border-divider pt-4 pb-[env(safe-area-inset-bottom,0px)]"
    >
      {NAV_ITEMS.filter((item) => !item.adminOnly || role === "admin").map(
        (item) => {
          const active = isNavItemActive(item, pathname);
          const Icon = item.Icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              title={item.label}
              className={`group relative flex flex-col items-center justify-center gap-0.5 w-14 h-14 rounded-md text-[11px] transition-all duration-200 ease-[var(--ease-out)] ${active
                ? "text-primary bg-primary/10 font-semibold"
                : "text-text-muted hover:bg-surface-2 hover:text-text"
                }`}
            >
              <span
                className={`absolute left-0 top-1/2 -translate-y-1/2 w-1 rounded-r-full bg-primary transition-all duration-300 ease-[var(--ease-spring)] ${active ? "h-7 opacity-100" : "h-0 opacity-0"}`}
              />
              <Icon
                className={`w-5 h-5 transition-transform duration-200 ease-[var(--ease-spring)] ${active ? "scale-110" : "group-active:scale-90"}`}
              />
              <span>{item.label}</span>
            </Link>
          );
        },
      )}
    </nav>
  );
}
