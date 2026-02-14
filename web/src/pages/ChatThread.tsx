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
  const abortRef = useRef<AbortController | null>(null);

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
          setMessages(data.messages || []);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load messages");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  // SSE connection for real-time updates
  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    (async () => {
      try {
        const token = await getOrMintToken("sse");
        await fetchEventSource(`${API_BASE}/p/${projectId}/events`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: ctrl.signal,
          onmessage(ev) {
            if (ev.event === "message.final") {
              try {
                const msg: Message = JSON.parse(ev.data);
                setMessages((prev) => {
                  if (prev.some((m) => m.id === msg.id)) return prev;
                  return [...prev, msg];
                });
              } catch {
                // ignore malformed messages
              }
            } else if (ev.event === "state.update") {
              // State updates can be handled here in the future
            }
          },
          onerror(err) {
            // fetchEventSource will auto-retry; log for debugging
            console.warn("SSE error, retrying…", err);
          },
          async onopen(response) {
            if (!response.ok) {
              throw new Error(`SSE connection failed (${response.status})`);
            }
          },
          openWhenHidden: true,
        });
      } catch {
        // Abort errors are expected on cleanup
      }
    })();

    return () => {
      ctrl.abort();
      abortRef.current = null;
    };
  }, [projectId]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);
    setError(null);

    // Optimistic local message
    const tempId = `temp-${Date.now()}`;
    const userMsg: Message = { id: tempId, role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/p/${projectId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: text }),
      });

      if (!res.ok) throw new Error(`Send failed (${res.status})`);

      const data = await res.json();
      // Replace temp message with server response
      if (data.message) {
        setMessages((prev) =>
          prev.map((m) => (m.id === tempId ? data.message : m)),
        );
      }
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
        <Button onClick={() => void handleSend()} disabled={sending || !input.trim()}>
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
