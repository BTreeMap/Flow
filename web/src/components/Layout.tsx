import { Outlet, Link } from "react-router";
import { useAuth } from "../auth";
import { Sun, Moon, Shield, LogOut, LayoutDashboard, Settings } from "lucide-react";
import { useState, useEffect } from "react";

export function Layout() {
  const { isAuthenticated, logout } = useAuth();
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    return document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <div className="min-h-screen bg-surface">
      <nav className="border-b border-border bg-surface/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center gap-2 font-bold text-lg text-text">
              <Shield className="w-5 h-5 text-primary" />
              <span>{"Flow"}</span>
            </Link>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setDark(!dark)}
                className="p-2 rounded-xl hover:bg-surface-alt transition-colors"
                aria-label="Toggle dark mode"
              >
                {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
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
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
