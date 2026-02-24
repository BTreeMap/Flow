import { useState, useRef, useCallback, useEffect } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useAuth, getOrMintToken } from "../auth";
import { Button } from "../components/Button";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Input } from "../components/Input";
import { PageHeader } from "../components/ui/PageHeader";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface LogEntry {
  time: string;
  text: string;
}

function timestamp(): string {
  return new Date().toLocaleTimeString();
}

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
          <Button
            onClick={() => void connect()}
            disabled={connected}
            data-testid="ws-connect"
          >
            Connect
          </Button>
          <Button
            onClick={disconnect}
            disabled={!connected}
            variant="danger"
            data-testid="ws-disconnect"
          >
            Disconnect
          </Button>
        </div>

        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded-lg bg-surface-alt p-3 text-xs font-mono text-text"
          data-testid="ws-log"
        >
          {wsLog.map((entry, i) => (
            <div key={i}>
              <span className="text-text-muted">{entry.time}</span> {entry.text}
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <Input
            type="text"
            value={wsInput}
            onChange={(e) => setWsInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Type a message…"
            className="flex-1"
            data-testid="ws-input"
          />
          <Button onClick={send} disabled={!connected} data-testid="ws-send">
            Send
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

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
          throw err;
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
      // expected on abort
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
          <Button
            onClick={() => void startStream()}
            disabled={streaming}
            data-testid="sse-start"
          >
            Start Stream
          </Button>
          <Button
            onClick={stopStream}
            disabled={!streaming}
            variant="danger"
            data-testid="sse-stop"
          >
            Stop Stream
          </Button>
        </div>

        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded-lg bg-surface-alt p-3 text-xs font-mono text-text"
          data-testid="sse-log"
        >
          {sseLog.map((entry, i) => (
            <div key={i}>
              <span className="text-text-muted">{entry.time}</span> {entry.text}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function DemoRealtime() {
  const { userId, deviceId } = useAuth();

  return (
    <div className="min-h-screen bg-bg">
      <PageHeader title="Realtime Demo" data-testid="realtime-heading" />

      <main className="mx-auto w-full max-w-5xl space-y-4 px-4 py-4">
        <p className="text-text-muted">
          Authenticated WebSocket &amp; SSE with device-key JWTs
          {userId && (
            <>
              {" "}· <span className="font-mono text-xs">{userId.slice(0, 8)}…</span>
            </>
          )}
          {deviceId && (
            <>
              {" "}·{" "}
              <span className="font-mono text-xs">{deviceId.slice(0, 8)}…</span>
            </>
          )}
        </p>

        <div className="grid gap-4 md:grid-cols-2">
          <WebSocketPanel />
          <SSEPanel />
        </div>
      </main>
    </div>
  );
}
