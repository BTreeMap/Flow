import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Bell, BellOff, MessageCircle, Download } from "lucide-react";
import { PageHeader } from "../components/ui/PageHeader";
import { ListRow } from "../components/ui/ListRow";
import { Button } from "../components/Button";
import { useInstallPrompt } from "../hooks/useInstallPrompt";
import { getOrMintToken } from "../auth/token";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface Membership {
  project_id: string;
  display_name: string | null;
  status: string;
}

export function Updates() {
  const { canPrompt, promptInstall, showIOSGuide, installed } =
    useInstallPrompt();

  const { data, isLoading } = useQuery<{ memberships: Membership[] }>({
    queryKey: ["dashboard"],
    queryFn: async () => {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load (${res.status})`);
      return res.json();
    },
  });

  const active =
    data?.memberships.filter((m) => m.status === "active") ?? [];

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      <PageHeader title="Updates" />

      <div className="flex-1">
        {/* Install CTA */}
        {canPrompt && !installed && (
          <div className="mx-4 mt-3 mb-1 flex items-center gap-3 p-3 bg-surface rounded-[var(--radius-md)] border border-border">
            <Download className="w-5 h-5 text-primary shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[14px] font-medium text-text">
                Install Flow
              </p>
              <p className="text-[12px] text-text-muted">
                {showIOSGuide
                  ? 'Tap Share → "Add to Home Screen"'
                  : "Get better notifications and quick access"}
              </p>
            </div>
            {!showIOSGuide && (
              <Button
                size="sm"
                onClick={() => void promptInstall()}
              >
                Install
              </Button>
            )}
          </div>
        )}

        {/* Notification status */}
        <div className="px-4 pt-4 pb-1">
          <p className="text-[12px] font-medium text-text-subtle uppercase tracking-wide">
            Notification Status
          </p>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
          </div>
        ) : active.length === 0 ? (
          <div className="text-center py-12 text-text-muted text-[14px]">
            No active projects yet.
          </div>
        ) : (
          active.map((m) => (
            <Link key={m.project_id} to={`/p/${m.project_id}/updates`}>
              <ListRow
                avatar={
                  <div className="w-10 h-10 rounded-full bg-surface-2 flex items-center justify-center">
                    <Bell className="w-5 h-5 text-primary" />
                  </div>
                }
                primary={m.display_name ?? m.project_id}
                secondary="View daily nudges"
                trailing={
                  <NotificationIndicator />
                }
              />
            </Link>
          ))
        )}

        {/* Projects quick links */}
        {active.length > 0 && (
          <>
            <div className="px-4 pt-4 pb-1">
              <p className="text-[12px] font-medium text-text-subtle uppercase tracking-wide">
                Quick Links
              </p>
            </div>
            {active.map((m) => (
              <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
                <ListRow
                  avatar={
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <MessageCircle className="w-5 h-5 text-primary" />
                    </div>
                  }
                  primary={m.display_name ?? m.project_id}
                  secondary="Open chat"
                />
              </Link>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function NotificationIndicator() {
  const supported =
    typeof Notification !== "undefined" && "PushManager" in window;
  const permission =
    typeof Notification !== "undefined" ? Notification.permission : "default";

  if (!supported) {
    return (
      <span className="flex items-center gap-1 text-[11px] text-text-subtle">
        <BellOff className="w-3 h-3" /> Not supported
      </span>
    );
  }

  if (permission === "granted") {
    return (
      <span className="flex items-center gap-1 text-[11px] text-success">
        <Bell className="w-3 h-3" /> Enabled
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1 text-[11px] text-text-subtle">
      <BellOff className="w-3 h-3" /> Not enabled
    </span>
  );
}
