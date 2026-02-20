import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, Link } from "react-router";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { getOrMintToken } from "../auth/token";
import { useAuth } from "../auth";
import { Send, Bell } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface Message {
  id: string;
  serverMsgId: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export function ChatThread() {
  const { projectId } = useParams<{ projectId: string }>();
  useAuth(); // ensure user is authenticated
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Load existing messages
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getOrMintToken("http");
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
                created_at?: string;
              }) => ({
                id: String(msg.message_id),
                serverMsgId: msg.server_msg_id,
                role: msg.role,
                content: msg.content,
                created_at: msg.created_at,
              }),
            ),
          );
          setLoading(false);
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

  // SSE connection for real-time updates
  useEffect(() => {
    const ctrl = new AbortController();
    let active = true;

    const appendMessage = (payload: {
      message_id: number;
      server_msg_id: string;
      role: "user" | "assistant";
      content: string;
      created_at?: string;
    }) => {
      const next: Message = {
        id: String(payload.message_id),
        serverMsgId: payload.server_msg_id,
        role: payload.role,
        content: payload.content,
        created_at: payload.created_at,
      };
      setMessages((prev) => {
        if (prev.some((m) => m.serverMsgId === next.serverMsgId)) return prev;
        return [...prev, next];
      });
    };

    (async () => {
      let retryCount = 0;
      while (active && !ctrl.signal.aborted) {
        try {
          const token = await getOrMintToken("sse");
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
                  appendMessage(
                    JSON.parse(ev.data) as {
                      message_id: number;
                      server_msg_id: string;
                      role: "user" | "assistant";
                      content: string;
                      created_at?: string;
                    },
                  );
                } catch {
                  // ignore malformed messages
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
            },
            openWhenHidden: true,
          });
        } catch {
          if (!active || ctrl.signal.aborted) {
            return;
          }
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
  }, [projectId]);

  const appendMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      if (prev.some((m) => m.serverMsgId === message.serverMsgId)) return prev;
      return [...prev, message];
    });
  }, []);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);
    setError(null);

    // Optimistic local message
    const tempId = `temp-${Date.now()}`;
    const userMsg: Message = {
      id: tempId,
      serverMsgId: tempId,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/p/${projectId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ text, client_msg_id: tempId }),
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
      };
      appendMessage({
        id: String(data.message_id),
        serverMsgId: data.server_msg_id,
        role: data.role,
        content: data.content,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
      // Remove optimistic message on failure
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-text">Chat</h1>
        <Link
          to={`/p/${projectId}/notifications`}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-xl hover:bg-surface-alt transition-colors text-text-muted"
        >
          <Bell className="w-4 h-4" />
          Notifications
        </Link>
      </div>

      {error && (
        <Alert variant="error" className="mb-4">
          {error}
        </Alert>
      )}

      {/* Messages */}
      <Card className="flex-1 overflow-y-auto mb-4">
        <div className="p-4 space-y-3">
          {messages.length === 0 && (
            <p className="text-center text-text-muted py-8">
              No messages yet. Start the conversation!
            </p>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-primary text-white"
                    : "bg-surface-alt text-text"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </Card>

      {/* Input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message…"
          className="flex-1 px-4 py-2.5 bg-surface border border-border rounded-2xl text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
          disabled={sending}
        />
        <Button
          onClick={() => void handleSend()}
          disabled={sending || !input.trim()}
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
