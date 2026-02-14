import { getOrMintToken } from "./token";

/**
 * Create an authenticated WebSocket connection.
 *
 * The token is passed in the URL query string (`?token=<jwt>`) because
 * the browser WebSocket API does not support custom headers.  The JWT
 * uses `aud = h4ckath0n:ws` to prevent cross-channel reuse.
 */
export async function createAuthWebSocket(
  url: string,
  onMessage?: (data: unknown) => void,
): Promise<WebSocket> {
  const token = await getOrMintToken("ws");
  const sep = url.includes("?") ? "&" : "?";
  const wsUrl = `${url}${sep}token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(wsUrl);

  if (onMessage) {
    ws.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data as string);
        onMessage(data);
      } catch {
        onMessage(event.data);
      }
    });
  }

  return ws;
}

/**
 * Send a re-auth message on an existing WebSocket when token is renewed.
 */
export async function sendReauth(ws: WebSocket): Promise<void> {
  if (ws.readyState !== WebSocket.OPEN) return;
  const token = await getOrMintToken("ws");
  ws.send(JSON.stringify({ type: "auth", token }));
}
