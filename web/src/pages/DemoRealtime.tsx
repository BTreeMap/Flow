import { useState, useRef, useCallback, useEffect } from "react";
import { useAuth, getOrMintToken } from "../auth";
import { Card, CardContent, CardHeader } from "../components/Card";
import { fetchEventSource } from "@microsoft/fetch-event-source";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface LogEntry {
  time: string;
  text: string;
}

function timestamp(): string {
  return new Date().toLocaleTimeString();
}

// ---------------------------------------------------------------------------
// WebSocket panel
// ---------------------------------------------------------------------------

function WebSocketPanel() {
  const [wsLog, setWsLog] = useState<LogEntry[]>([]);
  const [wsInput, setWsInput] = useState("");
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const addLog = useCallback((text: string) => {
    setWsLog((prev) => [...prev, { time: timestamp(), text }]);
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [wsLog]);

  const connect = useCallback(async () => {
    if (wsRef.current) return;
    try {
      const token = await getOrMintToken("ws");
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${proto}//${window.location.host}${API_BASE}/demo/ws?token=${encodeURIComponent(token)}`;
      const ws = new WebSocket(wsUrl);

      ws.addEventListener("open", () => {
        setConnected(true);
        addLog("[connected]");
      });
      ws.addEventListener("message", (event) => {
        try {
          const data = JSON.parse(event.data as string);
          addLog(JSON.stringify(data));
        } catch {
          addLog(String(event.data));
        }
      });
      ws.addEventListener("close", (event) => {
        setConnected(false);
        wsRef.current = null;
        addLog(`[closed code=${event.code} reason=${event.reason || "none"}]`);
      });
      ws.addEventListener("error", () => {
        addLog("[error]");
      });

      wsRef.current = ws;
    } catch (err) {
      addLog(`[error] ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [addLog]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const send = useCallback(() => {
    if (wsRef.current && wsInput.trim()) {
      wsRef.current.send(JSON.stringify({ message: wsInput.trim() }));
      addLog(`[sent] ${wsInput.trim()}`);
      setWsInput("");
    }
  }, [wsInput, addLog]);

  // cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg font-semibold text-text">WebSocket Demo</h2>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <button
            onClick={() => void connect()}
            disabled={connected}
            className="px-3 py-1.5 text-sm bg-primary text-white rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-50"
            data-testid="ws-connect"
          >
            Connect
          </button>
          <button
            onClick={disconnect}
            disabled={!connected}
            className="px-3 py-1.5 text-sm bg-danger text-white rounded-xl hover:opacity-80 transition-colors disabled:opacity-50"
            data-testid="ws-disconnect"
          >
            Disconnect
          </button>
        </div>

        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded-lg bg-surface-alt p-3 text-xs font-mono text-text"
          data-testid="ws-log"
        >
          {wsLog.map((entry, i) => (
            <div key={i}>
              <span className="text-text-muted">{entry.time}</span>{" "}
              {entry.text}
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={wsInput}
            onChange={(e) => setWsInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Type a message…"
            className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-border bg-surface text-text"
            data-testid="ws-input"
          />
          <button
            onClick={send}
            disabled={!connected}
            className="px-3 py-1.5 text-sm bg-primary text-white rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-50"
            data-testid="ws-send"
          >
            Send
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SSE panel
// ---------------------------------------------------------------------------

function SSEPanel() {
  const [sseLog, setSseLog] = useState<LogEntry[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const addLog = useCallback((text: string) => {
    setSseLog((prev) => [...prev, { time: timestamp(), text }]);
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [sseLog]);

  const startStream = useCallback(async () => {
    if (abortRef.current) return;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setSseLog([]);

    try {
      const token = await getOrMintToken("sse");
      await fetchEventSource(`${API_BASE}/demo/sse`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: ctrl.signal,
        openWhenHidden: true,
        onmessage(ev) {
          if (ev.event === "chunk") {
            addLog(`[chunk] ${ev.data}`);
          } else if (ev.event === "done") {
            addLog(`[done] ${ev.data}`);
          } else {
            addLog(`[${ev.event || "message"}] ${ev.data}`);
          }
        },
        onerror(err) {
          addLog(`[error] ${err instanceof Error ? err.message : String(err)}`);
          abortRef.current = null;
          setStreaming(false);
          throw err; // stop retrying
        },
        async onopen(response) {
          if (!response.ok) {
            addLog(`[error] HTTP ${response.status}`);
            abortRef.current = null;
            setStreaming(false);
            throw new Error(`HTTP ${response.status}`);
          }
          addLog("[stream opened]");
        },
        onclose() {
          addLog("[stream closed]");
          abortRef.current = null;
          setStreaming(false);
        },
      });
    } catch {
      // fetchEventSource may throw on abort – that's expected
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  }, [addLog]);

  const stopStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setStreaming(false);
    }
  }, []);

  // cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg font-semibold text-text">SSE Demo</h2>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <button
            onClick={() => void startStream()}
            disabled={streaming}
            className="px-3 py-1.5 text-sm bg-primary text-white rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-50"
            data-testid="sse-start"
          >
            Start Stream
          </button>
          <button
            onClick={stopStream}
            disabled={!streaming}
            className="px-3 py-1.5 text-sm bg-danger text-white rounded-xl hover:opacity-80 transition-colors disabled:opacity-50"
            data-testid="sse-stop"
          >
            Stop Stream
          </button>
        </div>

        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded-lg bg-surface-alt p-3 text-xs font-mono text-text"
          data-testid="sse-log"
        >
          {sseLog.map((entry, i) => (
            <div key={i}>
              <span className="text-text-muted">{entry.time}</span>{" "}
              {entry.text}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DemoRealtime() {
  const { userId, deviceId } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text" data-testid="realtime-heading">
          Realtime Demo
        </h1>
        <p className="text-text-muted">
          Authenticated WebSocket &amp; SSE with device-key JWTs
          {userId && <> · <span className="font-mono text-xs">{userId.slice(0, 8)}…</span></>}
          {deviceId && <> · <span className="font-mono text-xs">{deviceId.slice(0, 8)}…</span></>}
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <WebSocketPanel />
        <SSEPanel />
      </div>
    </div>
  );
}
