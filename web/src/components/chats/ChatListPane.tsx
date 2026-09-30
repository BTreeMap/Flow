import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare, Search } from "lucide-react";
import { Link, useParams } from "react-router";
import { getOrMintToken } from "../../auth/token";
import { ListRow } from "../ui/ListRow";
import { Avatar } from "./Avatar";
import {
  getDisplayPreview,
  isUnread,
  formatTime,
} from "../../utils/membership";
import type { DashboardResponse } from "../../api/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

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
      return (await res.json()) as DashboardResponse;
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
            onChange={(e) => { setSearch(e.target.value); }}
            data-testid="chat-search"
            className="w-full pl-9 pr-4 py-2 bg-surface-2 text-[16px] text-text placeholder:text-text-subtle rounded-pill border-none focus:outline-none focus-visible:ring-2 focus-visible:ring-focus transition-colors"
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
                  secondary={getDisplayPreview(m.last_message_preview)}
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
