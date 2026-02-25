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
import type { DashboardResponse, MembershipInfo } from "../api/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

function getLastOpenedAt(projectId: string): string | null {
  return localStorage.getItem(`chat-opened:${projectId}`);
}

function isUnread(m: MembershipInfo): boolean {
  if (!m.last_message_at) return false;
  const opened = getLastOpenedAt(m.project_id);
  if (!opened) return true;
  return m.last_message_at > opened;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7)
    return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function sortMemberships(memberships: MembershipInfo[] | undefined) {
  const mbs = memberships ?? [];
  const active = mbs.filter((m) => m.status === "active");
  const ended = mbs.filter((m) => m.status !== "active");

  // Sort active memberships by last_message_at descending
  active.sort((a, b) => {
    const aT = a.last_message_at ?? "";
    const bT = b.last_message_at ?? "";
    return bT.localeCompare(aT);
  });

  return { active, ended };
}

export function filterMemberships(
  sorted: { active: MembershipInfo[]; ended: MembershipInfo[] },
  search: string,
) {
  const { active, ended } = sorted;

  if (!search.trim()) return { active, ended };
  const q = search.toLowerCase();
  return {
    active: active.filter(
      (m) =>
        (m.display_name ?? "").toLowerCase().includes(q) ||
        (m.last_message_preview ?? "").toLowerCase().includes(q),
    ),
    ended: ended.filter((m) =>
      (m.display_name ?? "").toLowerCase().includes(q),
    ),
  };
}

function Avatar({ name }: { name: string }) {
  const initials = (name || "?")
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center text-[15px] font-semibold shrink-0">
      {initials}
    </div>
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  const layoutMode = useLayoutMode();
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
      return res.json();
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
    const urlMatch = code.match(/\/p\/([^/]+)\/activate/);
    if (urlMatch) {
      navigate(`/p/${urlMatch[1]}/activate`);
    } else {
      // Assume it's a project id or path
      navigate(code.startsWith("/") ? code : `/p/${code}/activate`);
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
    <div className="flex flex-col min-h-screen bg-bg" data-testid="dashboard-page">
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
            onChange={(e) => setSearch(e.target.value)}
            data-testid="chat-search"
            className="w-full pl-9 pr-4 py-2 bg-surface-2 text-[14px] text-text placeholder:text-text-subtle rounded-[var(--radius-pill)] border-none focus:outline-none focus-visible:ring-2 focus-visible:ring-focus transition-colors"
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
          <div className="flex flex-col items-center justify-center py-16 text-text-muted">
            <MessageSquare className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-[15px]">No chats yet</p>
            <p className="text-[13px] mt-1">
              Use an invite link to join a research project.
            </p>
          </div>
        )}

        {filtered.active.length > 0 &&
          filtered.active.map((m) => (
              <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
                <ListRow
                  avatar={<Avatar name={m.display_name ?? ""} />}
                  primary={m.display_name ?? m.project_id}
                  secondary={m.last_message_preview ?? "No messages yet"}
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
        onClick={() => setShowFab(true)}
        className="fixed bottom-[calc(var(--bottomnav-h)+env(safe-area-inset-bottom,0px)+16px)] right-4 w-14 h-14 rounded-full bg-primary text-on-primary shadow-md flex items-center justify-center hover:bg-primary-hover transition-colors z-40 md:bottom-6"
        aria-label="Join project"
      >
        <Plus className="w-6 h-6" />
      </button>

      {/* FAB modal */}
      {showFab && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/40">
          <div className="w-full max-w-sm mx-4 mb-4 md:mb-0 bg-surface rounded-[var(--radius-lg)] shadow-md p-5 space-y-4">
            <h2 className="text-[17px] font-semibold text-text">
              Join a Project
            </h2>
            <p className="text-[13px] text-text-muted">
              Paste an invite link or enter a project activation path.
            </p>
            <input
              type="text"
              placeholder="Invite link or /p/.../activate"
              value={inviteInput}
              onChange={(e) => setInviteInput(e.target.value)}
              className="w-full px-4 py-2.5 bg-surface-2 text-[14px] text-text placeholder:text-text-subtle rounded-[var(--radius-pill)] border border-border focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
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

