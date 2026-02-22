import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare, Search } from "lucide-react";
import { Link, useParams } from "react-router";
import { getOrMintToken } from "../../auth/token";
import { ListRow } from "../ui/ListRow";
import type { DashboardResponse, MembershipInfo } from "../../api/types";

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
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
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

interface ChatListPaneProps {
  /** When true, renders compact (inside side rail shell) */
  embedded?: boolean;
}

export function ChatListPane({ embedded }: ChatListPaneProps) {
  const { projectId: activeProjectId } = useParams<{ projectId: string }>();
  const [search, setSearch] = useState("");

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

  const memberships = data?.memberships ?? [];
  const active = memberships.filter((m) => m.status === "active");
  const ended = memberships.filter((m) => m.status !== "active");

  const filtered = useMemo(() => {
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
  }, [active, ended, search]);

  return (
    <div className="flex flex-col h-full" data-testid="chat-list-pane">
      {/* Header */}
      {!embedded && (
        <header className="sticky top-0 z-40 flex items-center justify-between h-[var(--header-h)] px-4 bg-surface/95 backdrop-blur-sm border-b border-divider">
          <h1 className="text-[17px] font-semibold text-text">Chats</h1>
        </header>
      )}
      {embedded && (
        <div className="px-4 pt-4 pb-1">
          <h2 className="text-[15px] font-semibold text-text">Chats</h2>
        </div>
      )}

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
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
          </div>
        )}

        {error && (
          <div className="px-4 mt-2 text-[13px] text-danger">
            {error instanceof Error ? error.message : "Failed to load chats"}
          </div>
        )}

        {!isLoading && memberships.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-16 text-text-muted">
            <MessageSquare className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-[15px]">No chats yet</p>
            <p className="text-[13px] mt-1">
              Use an invite link to join a research project.
            </p>
          </div>
        )}

        {filtered.active.length > 0 &&
          filtered.active
            .sort((a, b) => {
              const aT = a.last_message_at ?? "";
              const bT = b.last_message_at ?? "";
              return bT.localeCompare(aT);
            })
            .map((m) => (
              <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
                <ListRow
                  avatar={<Avatar name={m.display_name ?? ""} />}
                  primary={m.display_name ?? m.project_id}
                  secondary={m.last_message_preview ?? "No messages yet"}
                  unread={isUnread(m)}
                  className={
                    activeProjectId === m.project_id ? "bg-primary/5" : ""
                  }
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
    </div>
  );
}
