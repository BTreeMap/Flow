import { Outlet, Link } from "react-router";
import { useAuth } from "../auth";
import {
  ShieldCheck,
  Sun,
  Moon,
  Shield,
  LogOut,
  LayoutDashboard,
  Settings,
  Menu,
  X,
} from "lucide-react";
import { useState, useEffect } from "react";
import {
  applyEffectiveThemeForPreference,
  applyThemePreference,
  getEffectiveTheme,
  readThemePreference,
  subscribeToSystemThemeChanges,
  type ThemePreference,
} from "../theme";

export function Layout() {
  const { isAuthenticated, logout, role } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    typeof window === "undefined" ? "system" : readThemePreference(),
  );
  const [systemIsDark, setSystemIsDark] = useState(() =>
    typeof window === "undefined"
      ? false
      : getEffectiveTheme("system") === "dark",
  );
  const effectiveTheme: "light" | "dark" =
    themePreference === "system"
      ? systemIsDark
        ? "dark"
        : "light"
      : themePreference;

  useEffect(() => {
    applyThemePreference(themePreference);
    if (themePreference !== "system") return;
    return subscribeToSystemThemeChanges(() => {
      const effective = applyEffectiveThemeForPreference("system");
      setSystemIsDark(effective === "dark");
    });
  }, [themePreference]);

  useEffect(() => {
    const onPreferenceChange = () => {
      const pref = readThemePreference();
      setThemePreference(pref);
      if (pref === "system") {
        setSystemIsDark(getEffectiveTheme("system") === "dark");
      }
    };
    window.addEventListener("theme-preference-change", onPreferenceChange);
    return () =>
      window.removeEventListener("theme-preference-change", onPreferenceChange);
  }, []);

  return (
    <div className="min-h-screen bg-surface">
      <nav className="border-b border-border bg-surface/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link
              to="/"
              className="flex items-center gap-2 font-bold text-lg text-text"
            >
              <Shield className="w-5 h-5 text-primary" />
              <span>{"Flow"}</span>
            </Link>

            {/* Desktop nav */}
            <div className="hidden sm:flex items-center gap-3">
              <button
                onClick={() => {
                  if (themePreference === "system") {
                    setThemePreference(
                      effectiveTheme === "dark" ? "light" : "dark",
                    );
                    return;
                  }
                  setThemePreference(
                    themePreference === "light" ? "dark" : "light",
                  );
                }}
                className="p-2 rounded-xl hover:bg-surface-alt transition-colors"
                aria-label={
                  themePreference === "system"
                    ? `Theme: system (${effectiveTheme})`
                    : `Theme: ${themePreference}`
                }
              >
                {effectiveTheme === "dark" ? (
                  <Sun className="w-4 h-4" />
                ) : (
                  <Moon className="w-4 h-4" />
                )}
              </button>

              {isAuthenticated ? (
                <>
                  <Link
                    to="/dashboard"
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                    data-testid="nav-dashboard"
                  >
                    <LayoutDashboard className="w-4 h-4" />
                    Dashboard
                  </Link>
                  <Link
                    to="/settings"
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                    data-testid="nav-settings"
                  >
                    <Settings className="w-4 h-4" />
                    Settings
                  </Link>
                  {role === "admin" && (
                    <Link
                      to="/admin"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                      data-testid="nav-admin"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      Admin
                    </Link>
                  )}
                  <button
                    onClick={() => void logout()}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl hover:bg-surface-alt transition-colors text-danger"
                    data-testid="nav-logout"
                  >
                    <LogOut className="w-4 h-4" />
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="px-3 py-1.5 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                  >
                    Login
                  </Link>
                  <Link
                    to="/register"
                    className="px-4 py-1.5 text-sm bg-primary text-white rounded-xl hover:bg-primary-hover transition-colors"
                  >
                    Register
                  </Link>
                </>
              )}
            </div>

            {/* Mobile hamburger */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="sm:hidden p-2 rounded-xl hover:bg-surface-alt transition-colors"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? (
                <X className="w-5 h-5" />
              ) : (
                <Menu className="w-5 h-5" />
              )}
            </button>
          </div>

          {/* Mobile menu */}
          {mobileMenuOpen && (
            <div className="sm:hidden pb-3 space-y-1">
              <button
                onClick={() => {
                  if (themePreference === "system") {
                    setThemePreference(
                      effectiveTheme === "dark" ? "light" : "dark",
                    );
                  } else {
                    setThemePreference(
                      themePreference === "light" ? "dark" : "light",
                    );
                  }
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors"
              >
                {effectiveTheme === "dark" ? (
                  <Sun className="w-4 h-4" />
                ) : (
                  <Moon className="w-4 h-4" />
                )}
                Theme
              </button>

              {isAuthenticated ? (
                <>
                  <Link
                    to="/dashboard"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                    data-testid="nav-dashboard-mobile"
                  >
                    <LayoutDashboard className="w-4 h-4" />
                    Dashboard
                  </Link>
                  <Link
                    to="/settings"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                    data-testid="nav-settings-mobile"
                  >
                    <Settings className="w-4 h-4" />
                    Settings
                  </Link>
                  {role === "admin" && (
                    <Link
                      to="/admin"
                      onClick={() => setMobileMenuOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                      data-testid="nav-admin-mobile"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      Admin
                    </Link>
                  )}
                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      void logout();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors text-danger"
                    data-testid="nav-logout-mobile"
                  >
                    <LogOut className="w-4 h-4" />
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors"
                  >
                    Login
                  </Link>
                  <Link
                    to="/register"
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-xl hover:bg-surface-alt transition-colors text-primary"
                  >
                    Register
                  </Link>
                </>
              )}
            </div>
          )}
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
