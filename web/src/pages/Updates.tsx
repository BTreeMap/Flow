import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Bell, Download, Clock } from "lucide-react";
import { PageHeader } from "../components/ui/PageHeader";
import { Button } from "../components/Button";
import { useInstallPrompt } from "../hooks/useInstallPrompt";
import api from "../api/client";
import type { UnifiedNotificationItem } from "../api/types";

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export function Updates() {
  const { canPrompt, promptInstall, showIOSGuide, installed } =
    useInstallPrompt();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery<UnifiedNotificationItem[]>({
    queryKey: ["unified-notifications"],
    queryFn: async () => {
      const { data: respData, error: respError } = await api.GET(
        "/notifications",
      );
      if (respError) throw new Error("Failed to load notifications");
      return respData.notifications;
    },
  });

  const markReadMutation = useMutation({
    mutationFn: async (notificationId: number) => {
      await api.POST("/notifications/{notification_id}/read", {
        params: { path: { notification_id: notificationId } },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["unified-notifications"] });
    },
  });

  const notifications = data ?? [];

  const handleClick = (n: UnifiedNotificationItem) => {
    if (!n.read_at) {
      markReadMutation.mutate(n.id);
    }
    navigate(`/p/${n.project_id}/chat?nid=${n.id}`);
  };

  return (
    <div className="flex flex-col flex-1 bg-bg">
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

        {/* Unified notifications feed */}
        <div className="px-4 pt-4 pb-1">
          <p className="text-[12px] font-medium text-text-subtle uppercase tracking-wide">
            Recent Notifications
          </p>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
          </div>
        ) : error ? (
          <div className="text-center py-12 text-text-muted text-[14px]">
            Failed to load notifications.
          </div>
        ) : notifications.length === 0 ? (
          <div className="text-center py-12 text-text-muted text-[14px]">
            No notifications yet.
          </div>
        ) : (
          notifications.map((n) => (
            <button
              key={n.id}
              type="button"
              className={`w-full text-left px-4 py-3 border-b border-border hover:bg-surface-2 transition-colors ${!n.read_at ? "bg-primary/5" : ""}`}
              onClick={() => handleClick(n)}
            >
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${!n.read_at ? "bg-primary/20" : "bg-surface-2"}`}>
                  <Bell className={`w-5 h-5 ${!n.read_at ? "text-primary" : "text-text-subtle"}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className={`text-[14px] truncate ${!n.read_at ? "font-semibold text-text" : "font-medium text-text-muted"}`}>
                      {n.title}
                    </p>
                    <span className="text-[11px] text-text-subtle shrink-0 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {relativeTime(n.created_at)}
                    </span>
                  </div>
                  <p className="text-[13px] text-text-muted mt-0.5 line-clamp-2">
                    {n.body}
                  </p>
                  <p className="text-[11px] text-text-subtle mt-1">
                    {n.project_display_name ?? n.project_id}
                  </p>
                </div>
                {!n.read_at && (
                  <div className="w-2 h-2 rounded-full bg-primary shrink-0 mt-2" />
                )}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
