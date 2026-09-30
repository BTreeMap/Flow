import { Link, useLocation } from "react-router";
import { NAV_ITEMS, isNavItemActive } from "../../config/nav";

export function BottomNav() {
  const { pathname } = useLocation();
  const items = NAV_ITEMS.filter((item) => !item.adminOnly);

  return (
    <nav aria-label="Main navigation" data-testid="bottom-nav" className="fixed bottom-0 inset-x-0 z-50 bg-surface/85 backdrop-blur-xl border-t border-divider" style={{ height: "calc(var(--bottomnav-h) + env(safe-area-inset-bottom, 0px))", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
      <div className="flex items-center justify-around h-[var(--bottomnav-h)]">
        {items.map((item) => {
          const active = isNavItemActive(item, pathname);
          const Icon = item.Icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              className={`group relative flex flex-col items-center justify-center gap-0.5 min-w-[var(--tap)] h-[var(--tap)] text-[11px] transition-colors duration-200 ${active
                ? "text-primary font-semibold"
                : "text-text-muted hover:text-text"
                }`}
            >
              <span
                className={`absolute -top-px h-0.5 w-7 rounded-full bg-primary transition-all duration-300 ease-[var(--ease-spring)] ${active ? "opacity-100 scale-x-100" : "opacity-0 scale-x-0"}`}
              />
              <Icon
                className={`w-5 h-5 transition-transform duration-200 ease-[var(--ease-spring)] ${active ? "scale-110 -translate-y-px" : "group-active:scale-90"}`}
              />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
