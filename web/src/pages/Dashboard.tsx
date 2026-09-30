import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert } from "../components/Alert";
import { MessageSquare, Plus, Download, Search } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { getOrMintToken } from "../auth/token";
import { PageHeader } from "../components/ui/PageHeader";
import { ListRow } from "../components/ui/ListRow";
import { Button } from "../components/Button";
import { useInstallPrompt } from "../hooks/useInstallPrompt";
import { useLayoutMode } from "../hooks/useLayoutMode";
import { useTimezone } from "../hooks/useTimezone";
import { Avatar } from "../components/chats/Avatar";
import {
  getDisplayPreview,
  isUnread,
  formatTime,
  sortMemberships,
  filterMemberships,
} from "../utils/membership";
import type { DashboardResponse } from "../api/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export function Dashboard() {
  const navigate = useNavigate();
  const layoutMode = useLayoutMode();
  useTimezone();
  const [search, setSearch] = useState("");
  const { canPrompt, promptInstall, showIOSGuide } = useInstallPrompt();
  const [showFab, setShowFab] = useState(false);
  const [inviteInput, setInviteInput] = useState("");

  const { data, isLoading, error } = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: async () => {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load chats (${res.status})`);
      return (await res.json()) as DashboardResponse;
    },
  });

  const memberships = data?.memberships;

  // Split memoization into two levels:
  // 1. Sort and group (expensive, depends only on memberships)
  // 2. Filter by search query (cheap, depends on sorted list + search)
  const sortedMemberships = useMemo(
    () => sortMemberships(memberships),
    [memberships],
  );

  const filtered = useMemo(
    () => filterMemberships(sortedMemberships, search),
    [sortedMemberships, search],
  );

  const handleJoinFromFab = () => {
    const code = inviteInput.trim();
    if (!code) return;
    // Try to parse as a full URL or just a code
    const urlMatch = /\/p\/([^/]+)\/activate/.exec(code);
    if (urlMatch) {
      void navigate(`/p/${urlMatch[1]}/activate`);
    } else {
      // Assume it's a project id or path
      void navigate(code.startsWith("/") ? code : `/p/${code}/activate`);
    }
    setShowFab(false);
    setInviteInput("");
  };

  // In side mode, the chat list is rendered by the shell's ChatListPane.
  // The main pane shows a placeholder.
  if (layoutMode === "side") {
    return (
      <div className="flex flex-col h-full bg-surface-2" data-testid="dashboard-page">
        <PageHeader title="Chats" data-testid="dashboard-heading" />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-text-muted">
            <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-[15px]">Select a chat to start messaging</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 bg-bg" data-testid="dashboard-page">
      <PageHeader
        title="Chats"
        data-testid="dashboard-heading"
        actions={
          canPrompt ? (
            <button
              onClick={() => void (showIOSGuide ? null : promptInstall())}
              className="flex items-center gap-1 px-2.5 py-1 text-[12px] font-medium text-primary bg-primary/10 rounded-full hover:bg-primary/20 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Install
            </button>
          ) : undefined
        }
      />

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-subtle" />
          <input
            type="text"
            placeholder="Search"
            value={search}
            onChange={(e) => { setSearch(e.target.value); }}
            data-testid="chat-search"
            className="w-full pl-9 pr-4 py-2 bg-surface-2 text-[16px] text-text placeholder:text-text-subtle rounded-pill border-none focus:outline-none focus-visible:ring-2 focus-visible:ring-focus transition-colors"
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
          </div>
        )}

        {error && (
          <div className="px-4 mt-2">
            <Alert variant="error">
              {error instanceof Error
                ? error.message
                : "Failed to load chats"}
            </Alert>
          </div>
        )}

        {!isLoading && (memberships?.length ?? 0) === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-20 px-6 text-center">
            <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-primary/15 to-accent/10 flex items-center justify-center mb-4 ring-1 ring-inset ring-primary/10">
              <MessageSquare className="w-7 h-7 text-primary" />
            </div>
            <p className="text-[16px] font-semibold text-text">No chats yet</p>
            <p className="text-[13px] text-text-muted mt-1 max-w-[15rem]">
              Use an invite link to join a research project and start coaching.
            </p>
          </div>
        )}

        {filtered.active.length > 0 &&
          filtered.active.map((m) => (
            <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
              <ListRow
                avatar={<Avatar name={m.display_name ?? ""} />}
                primary={m.display_name ?? m.project_id}
                secondary={getDisplayPreview(m.last_message_preview)}
                unread={isUnread(m)}
                trailing={
                  m.last_message_at ? (
                    <span className="text-[11px] text-text-subtle whitespace-nowrap">
                      {formatTime(m.last_message_at)}
                    </span>
                  ) : undefined
                }
              />
            </Link>
          ))}

        {filtered.ended.length > 0 && (
          <>
            <div className="px-4 pt-4 pb-1">
              <p className="text-[12px] font-medium text-text-subtle uppercase tracking-wide">
                Ended
              </p>
            </div>
            {filtered.ended.map((m) => (
              <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
                <div className="opacity-50">
                  <ListRow
                    avatar={<Avatar name={m.display_name ?? ""} />}
                    primary={m.display_name ?? m.project_id}
                    secondary="Ended"
                  />
                </div>
              </Link>
            ))}
          </>
        )}
      </div>

      {/* FAB */}
      <button
        onClick={() => { setShowFab(true); }}
        className="fixed right-4 w-14 h-14 rounded-lg bg-primary text-on-primary shadow-primary flex items-center justify-center hover:bg-primary-hover hover:scale-105 hover:shadow-lg active:scale-95 transition-all duration-200 ease-[var(--ease-spring)] z-40"
        style={{ bottom: "calc(var(--bottomnav-h) + env(safe-area-inset-bottom, 0px) + 16px)" }}
        aria-label="Join project"
      >
        <Plus className="w-6 h-6" />
      </button>

      {/* FAB modal */}
      {showFab && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-cream-950/50 backdrop-blur-sm">
          <div className="w-full max-w-sm mx-4 mb-4 md:mb-0 bg-surface border border-border rounded-xl shadow-lg p-6 space-y-4">
            <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-text">
              Join a Project
            </h2>
            <p className="text-[13px] text-text-muted">
              Paste an invite link or enter a project activation path.
            </p>
            <input
              type="text"
              placeholder="Invite link or /p/.../activate"
              value={inviteInput}
              onChange={(e) => { setInviteInput(e.target.value); }}
              className="w-full px-4 py-2.5 bg-surface-2 text-[16px] text-text placeholder:text-text-subtle rounded-pill border border-border focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") handleJoinFromFab();
              }}
            />
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowFab(false);
                  setInviteInput("");
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleJoinFromFab}
                disabled={!inviteInput.trim()}
              >
                Go
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
