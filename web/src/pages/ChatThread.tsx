import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { Alert } from "../components/Alert";
import { getOrMintToken } from "../auth/token";
import { useAuth } from "../auth";
import { ChevronDown } from "lucide-react";
import { ChatHeader } from "../components/ui/ChatHeader";
import { MessageBubble } from "../components/ui/MessageBubble";
import { Composer } from "../components/ui/Composer";
import { useLayoutMode } from "../hooks/useLayoutMode";
import { useTimezone } from "../hooks/useTimezone";
import type { DashboardResponse, FeedbackPollMetadata } from "../api/types";
import api from "../api/client";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface DebugInfo {
  agent?: string;
  condition?: string;
  prompt_args?: Record<string, unknown>;
  tools?: string[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  tool_calls?: any[];
}

interface Message {
  id: string;
  serverMsgId: string;
  role: "user" | "assistant";
  content: string;
  metadata?: FeedbackPollMetadata | Record<string, unknown>;
  created_at?: string;
  isStreaming?: boolean;
  debugInfo?: DebugInfo;
}

function isSystemContent(content: string): boolean {
  return content.startsWith("[System:");
}

function formatBubbleTime(iso?: string): string | undefined {
  if (!iso) return undefined;
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function shouldGroup(prev: Message | undefined, curr: Message): boolean {
  if (!prev || prev.role !== curr.role) return false;
  if (!prev.created_at || !curr.created_at) return false;
  const diff =
    new Date(curr.created_at).getTime() - new Date(prev.created_at).getTime();
  return diff < 2 * 60 * 1000; // 2 minutes
}

function debugInfoFromMetadata(
  metadata: FeedbackPollMetadata | Record<string, unknown> | undefined,
): DebugInfo | undefined {
  if (!metadata || typeof metadata !== "object") return undefined;
  const debugInfo = (metadata as Record<string, unknown>).debug_info;
  if (!debugInfo || typeof debugInfo !== "object") return undefined;
  return debugInfo as DebugInfo;
}

export function ChatThread() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  useAuth();
  useTimezone();
  const queryClient = useQueryClient();
  const layoutMode = useLayoutMode();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionStatus, setConnectionStatus] = useState<
    "online" | "reconnecting" | "offline"
  >("online");
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [currentNotificationId, setCurrentNotificationId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastEventIdRef = useRef<string | null>(null);
  const [chatTitle, setChatTitle] = useState("Chat");

  // Mark chat as opened for unread tracking
  useEffect(() => {
    if (projectId) {
      localStorage.setItem(`chat-opened:${projectId}`, new Date().toISOString());
    }
  }, [projectId]);

  // Handle push notification interaction (nid param)
  useEffect(() => {
    const nid = searchParams.get("nid");
    const parsedNid = nid ? parseInt(nid, 10) : NaN;
    if (!Number.isNaN(parsedNid) && projectId) {
      // Safe to carry this id client-side: backend re-verifies user+membership scope
      // before cancelling any scheduled feedback task.
      setCurrentNotificationId(parsedNid);
      // Clear param immediately so we don't re-trigger
      const newParams = new URLSearchParams(searchParams);
      newParams.delete("nid");
      setSearchParams(newParams, { replace: true });

      // Call mark-read (unified global endpoint)
      (async () => {
        try {
          await api.POST(
            "/notifications/{notification_id}/read",
            {
              params: {
                path: {
                  notification_id: parsedNid,
                },
              },
            },
          );
        } catch (err) {
          console.error("Failed to mark notification read", err);
        }
      })();
    }
  }, [projectId, searchParams, setSearchParams]);

  const isNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (!showJumpToBottom) {
      scrollToBottom();
    } else {
      setHasNewMessages(true);
    }
  }, [messages, showJumpToBottom, scrollToBottom]);

  // Track scroll position for jump-to-bottom
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const nearBottom = isNearBottom();
      setShowJumpToBottom(!nearBottom);
      if (nearBottom) {
        setHasNewMessages(false);
      }
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [isNearBottom]);

  // Load existing messages
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getOrMintToken("http");

        // Fetch dashboard for chat title
        const dashRes = await fetch(`${API_BASE}/dashboard`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (dashRes.ok) {
          const dashData = await dashRes.json();
          const membership = (dashData.memberships ?? []).find(
            (m: { project_id: string }) => m.project_id === projectId,
          );
          if (membership?.display_name) {
            setChatTitle(membership.display_name);
          }
        }

        const res = await fetch(`${API_BASE}/p/${projectId}/messages`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Failed to load messages (${res.status})`);
        const data = await res.json();
        if (!cancelled) {
          setMessages(
            (data.messages || []).map(
              (msg: {
                message_id: number;
                server_msg_id: string;
                role: "user" | "assistant";
                content: string;
                metadata?: FeedbackPollMetadata | Record<string, unknown>;
                created_at?: string;
                debug_info?: DebugInfo;
              }) => ({
                id: String(msg.message_id),
                serverMsgId: msg.server_msg_id,
                role: msg.role,
                content: msg.content,
                metadata: msg.metadata,
                created_at: msg.created_at,
                debugInfo: msg.debug_info ?? debugInfoFromMetadata(msg.metadata),
              }),
            ),
          );
          setLoading(false);
          // Scroll to bottom after initial load
          setTimeout(() => bottomRef.current?.scrollIntoView(), 50);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load messages",
          );
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Update dashboard helper
  const updateDashboardPreview = useCallback((preview: string, timestamp?: string) => {
    queryClient.setQueryData<DashboardResponse>(["dashboard"], (old) => {
      if (!old || !projectId) return old;
      return {
        ...old,
        memberships: old.memberships.map((m) => {
          if (m.project_id === projectId) {
            return {
              ...m,
              last_message_preview: preview,
              last_message_at: timestamp || m.last_message_at, // Keep old time if pending
            };
          }
          return m;
        }),
      };
    });
  }, [projectId, queryClient]);

  // SSE connection for real-time updates
  useEffect(() => {
    const ctrl = new AbortController();
    let active = true;

    const appendSSEMessage = (payload: {
      message_id: number;
      server_msg_id: string;
      role: "user" | "assistant";
      content: string;
      metadata?: FeedbackPollMetadata | Record<string, unknown>;
      created_at?: string;
      debug_info?: DebugInfo;
    }) => {
      setMessages((prev) => {
        // If message already exists (e.g. from stream), update it with final content and unset streaming
        if (prev.some((m) => m.serverMsgId === payload.server_msg_id)) {
          return prev.map((m) => {
            if (m.serverMsgId === payload.server_msg_id) {
                return {
                  ...m,
                  id: String(payload.message_id), // Ensure ID is sync
                  content: payload.content,
                  metadata: payload.metadata,
                  isStreaming: false,
                  created_at: payload.created_at,
                  debugInfo:
                    payload.debug_info ?? debugInfoFromMetadata(payload.metadata),
                };
              }
            return m;
          });
        }
        // Otherwise append new
        const next: Message = {
          id: String(payload.message_id),
          serverMsgId: payload.server_msg_id,
          role: payload.role,
          content: payload.content,
          metadata: payload.metadata,
          created_at: payload.created_at,
          isStreaming: false,
          debugInfo: payload.debug_info ?? debugInfoFromMetadata(payload.metadata),
        };
        return [...prev, next];
      });
      // Locally update dashboard
      updateDashboardPreview(payload.content, payload.created_at);
    };

    const handleSSEChunk = (payload: {
      server_msg_id: string;
      delta: string;
    }) => {
      setMessages((prev) => {
        // Find existing message or append new placeholder
        if (prev.some((m) => m.serverMsgId === payload.server_msg_id)) {
          return prev.map((m) => {
            if (m.serverMsgId === payload.server_msg_id) {
              return {
                ...m,
                content: m.content + payload.delta,
                isStreaming: true,
              };
            }
            return m;
          });
        }
        // Create placeholder
        const next: Message = {
          id: `stream-${payload.server_msg_id}`,
          serverMsgId: payload.server_msg_id,
          role: "assistant",
          content: payload.delta,
          created_at: new Date().toISOString(),
          isStreaming: true,
        };
        return [...prev, next];
      });
    };

    const handleMessageUpdated = (payload: {
      message_id: number;
      server_msg_id?: string;
      metadata: FeedbackPollMetadata | Record<string, unknown>;
    }) => {
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id === String(payload.message_id)) {
            return { ...m, metadata: payload.metadata };
          }
          if (payload.server_msg_id && m.serverMsgId === payload.server_msg_id) {
            return { ...m, metadata: payload.metadata };
          }
          return m;
        }),
      );
    };

    (async () => {
      let retryCount = 0;
      while (active && !ctrl.signal.aborted) {
        try {
          const token = await getOrMintToken("sse");
          if (retryCount > 0) {
            setConnectionStatus("reconnecting");
          }
          await fetchEventSource(`${API_BASE}/p/${projectId}/events`, {
            headers: {
              Authorization: `Bearer ${token}`,
              ...(lastEventIdRef.current
                ? { "Last-Event-ID": lastEventIdRef.current }
                : {}),
            },
            signal: ctrl.signal,
            onmessage(ev) {
              if (ev.id) {
                lastEventIdRef.current = ev.id;
              }
              if (ev.event === "message.final") {
                try {
                  appendSSEMessage(
                    JSON.parse(ev.data) as {
                      message_id: number;
                      server_msg_id: string;
                      role: "user" | "assistant";
                      content: string;
                      metadata?: FeedbackPollMetadata | Record<string, unknown>;
                      created_at?: string;
                      debug_info?: DebugInfo;
                    },
                  );
                } catch {
                  // ignore malformed messages
                }
              } else if (ev.event === "message.updated") {
                try {
                  handleMessageUpdated(
                    JSON.parse(ev.data) as {
                      message_id: number;
                      server_msg_id?: string;
                      metadata: FeedbackPollMetadata | Record<string, unknown>;
                    },
                  );
                } catch {
                  // ignore malformed updates
                }
              } else if (ev.event === "message.chunk") {
                try {
                  handleSSEChunk(
                    JSON.parse(ev.data) as {
                      server_msg_id: string;
                      delta: string;
                    },
                  );
                } catch {
                  // ignore
                }
              }
            },
            async onopen(response) {
              if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                  setError("Your session expired. Please log in again.");
                  ctrl.abort();
                  throw new Error("auth");
                }
                throw new Error(`SSE connection failed (${response.status})`);
              }
              retryCount = 0;
              setConnectionStatus("online");
            },
            openWhenHidden: true,
          });
        } catch {
          if (!active || ctrl.signal.aborted) {
            return;
          }
          setConnectionStatus("reconnecting");
          retryCount += 1;
          const backoffMs = Math.min(1000 * 2 ** (retryCount - 1), 10000);
          await new Promise((resolve) => setTimeout(resolve, backoffMs));
        }
      }
    })();

    return () => {
      active = false;
      ctrl.abort();
    };
  }, [projectId, queryClient, updateDashboardPreview]);

  const handleSend = async (text: string) => {
    if (!text || sending) return;

    setSending(true);
    setError(null);

    const tempId = `temp-${Date.now()}`;
    const userMsg: Message = {
      id: tempId,
      serverMsgId: tempId,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setTimeout(() => {
      scrollToBottom();
      setShowJumpToBottom(false);
      setHasNewMessages(false);
    }, 0);

    // Optimistically update dashboard
    updateDashboardPreview(text, userMsg.created_at);

    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/p/${projectId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          text,
          client_msg_id: tempId,
          current_notification_id: currentNotificationId,
        }),
      });

      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          throw new Error("Your session expired. Please log in again.");
        }
        throw new Error(`Send failed (${res.status})`);
      }

      const data = (await res.json()) as {
        message_id: number;
        server_msg_id: string;
        role: "user" | "assistant";
        content: string;
        user_message?: {
          message_id: number;
          server_msg_id: string;
          role: "user" | "assistant";
          content: string;
          created_at: string;
        };
        debug_info?: DebugInfo;
      };
      setMessages((prev) => {
        // Remove the temporary message
        const next = prev.filter((m) => m.id !== tempId);

        // Add the real user message if returned (replacing temp)
        if (data.user_message) {
          // Avoid duplicate if already present
          if (
            !next.some((m) => m.serverMsgId === data.user_message!.server_msg_id)
          ) {
            next.push({
              id: String(data.user_message.message_id),
              serverMsgId: data.user_message.server_msg_id,
              role: data.user_message.role,
              content: data.user_message.content,
              created_at: data.user_message.created_at,
            });
          }
        }

        // Add or update the assistant message (in case streaming started)
        const asstIdx = next.findIndex(
          (m) => m.serverMsgId === data.server_msg_id,
        );
        if (asstIdx !== -1) {
          next[asstIdx] = {
            ...next[asstIdx],
            id: String(data.message_id),
            serverMsgId: data.server_msg_id,
            role: data.role,
            content: data.content,
            created_at: data.user_message?.created_at || new Date().toISOString(),
            isStreaming: false,
            debugInfo: data.debug_info,
          };
        } else {
          next.push({
            id: String(data.message_id),
            serverMsgId: data.server_msg_id,
            role: data.role,
            content: data.content,
            created_at: new Date().toISOString(),
            isStreaming: false,
            debugInfo: data.debug_info,
          });
        }
        return next;
      });
      // Locally update dashboard with final assistant message
      updateDashboardPreview(data.content);
      setCurrentNotificationId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
    } finally {
      setSending(false);
      // Update last opened
      if (projectId) {
        localStorage.setItem(
          `chat-opened:${projectId}`,
          new Date().toISOString(),
        );
      }
    }
  };

  const groupedMessages = useMemo(() => {
    // Sorting Logic:
    // 1. Persisted messages (numeric ID) -> sort by ID ascending.
    // 2. Pending User Messages (temp-*) -> sort by creation time (although usually just one).
    // 3. Streaming Assistant Messages (stream-*) -> sort by creation time (usually just one).
    //
    // Final order: [ ...Persisted, ...PendingUser, ...StreamingAssistant ]
    // This ensures pending/streaming always appear at the bottom until confirmed/persisted.

    const persisted: Message[] = [];
    const pendingUser: Message[] = [];
    const streamingAssistant: Message[] = [];

    messages.forEach(m => {
        if (m.id.startsWith("temp-")) {
            pendingUser.push(m);
        } else if (m.id.startsWith("stream-")) {
            streamingAssistant.push(m);
        } else {
            persisted.push(m);
        }
    });

    persisted.sort((a, b) => Number(a.id) - Number(b.id));
    pendingUser.sort((a, b) => new Date(a.created_at!).getTime() - new Date(b.created_at!).getTime());
    streamingAssistant.sort((a, b) => new Date(a.created_at!).getTime() - new Date(b.created_at!).getTime());

    const sorted = [...persisted, ...pendingUser, ...streamingAssistant].filter(
      (m) => !isSystemContent(m.content),
    );

    return sorted.map((msg, i) => ({
      ...msg,
      isGroupContinuation: shouldGroup(sorted[i - 1], msg),
    }));
  }, [messages]);

  if (loading) {
    return (
      <div className="flex items-center justify-center flex-1 bg-chat-bg">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className={`flex flex-col bg-chat-bg ${layoutMode === "side" ? "h-full" : "flex-1 min-h-0"}`}>
      <ChatHeader
        title={chatTitle}
        hideBack={layoutMode === "side"}
        avatar={
          <div className="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center text-[13px] font-semibold">
            {(chatTitle[0] ?? "C").toUpperCase()}
          </div>
        }
        connectionStatus={connectionStatus}
        menuItems={[
          {
            label: "Updates",
            onClick: () => navigate(`/p/${projectId}/updates`),
          },
          {
            label: "Notification Settings",
            onClick: () => navigate(`/p/${projectId}/notifications`),
          },
        ]}
        debugMode={debugMode}
        onToggleDebug={() => setDebugMode(!debugMode)}
      />

      {error && (
        <div className="px-3 pt-2">
          <Alert variant="error">{error}</Alert>
        </div>
      )}

      {/* Message list */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-3 py-2"
      >
        {messages.length === 0 && (
          <p className="text-center text-text-muted py-12 text-[14px]">
            No messages yet. Start the conversation!
          </p>
        )}
        {groupedMessages.map((msg) => (
          <MessageBubble
            key={msg.id}
            projectId={projectId}
            role={msg.role}
            content={msg.content}
            metadata={msg.metadata}
            timestamp={formatBubbleTime(msg.created_at)}
            isGroupContinuation={msg.isGroupContinuation}
            isStreaming={msg.isStreaming}
            debugInfo={msg.debugInfo}
            showDebug={debugMode}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Jump to bottom */}
      {showJumpToBottom && (
        <div className="relative z-30">
          <button
            onClick={scrollToBottom}
            className={`absolute bottom-3 right-4 w-10 h-10 rounded-full shadow-md flex items-center justify-center transition-colors ${
              hasNewMessages
                ? "bg-primary text-primary-foreground hover:bg-primary/90"
                : "bg-surface text-text-muted hover:bg-surface-2"
            }`}
            aria-label="Jump to bottom"
            data-testid="jump-to-bottom"
          >
            <ChevronDown className="w-5 h-5" />
          </button>
        </div>
      )}

      <Composer onSend={(text) => void handleSend(text)} disabled={sending} />
    </div>
  );
}
