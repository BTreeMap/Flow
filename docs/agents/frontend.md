# Frontend, PWA, SSE & Web Push

React PWA in [`web/`](../../web/). Auth is passkey-first via the h4ckath0n scaffold — do
not implement auth from scratch.

## Required pages
- **Dashboard** — list project threads; active shown normally, ended greyed out but visible.
- **Activation** — join a project via invite link; collect optional email **contact**
  (never identity).
- **Chat thread** — send via `POST`, receive via SSE, render streaming updates.
- **Notifications** — iOS "Add to Home Screen" guidance **before** enabling notifications;
  enable via explicit user button; subscribe and register with backend; show status.

## Delivery plane
- Foreground chat uses **SSE** as the mandatory default. Implement the SSE client with
  reconnect (send `Last-Event-ID` to replay missed events — the backend persists events
  for durable replay).
- WebSocket is optional only behind a feature flag and is not required for acceptance.

## Web Push (vendor-neutral only)
- Register a service worker.
- Request permission via an explicit user action.
- Subscribe with the VAPID public key fetched from the backend; store subscription
  crypto keys server-side (per membership/device).
- Service worker handles `push` (show notification) and `notificationclick` (deep-link to
  the correct project thread).
- Never log push crypto keys.

## OpenAPI contract sync (required)
If backend request/response models change, regenerate frontend types in the **same**
change:

```bash
cd web
npm run gen:api:check   # fails if web/src/api/openapi.ts is stale
npm run gen:api         # regenerate, then commit web/src/api/openapi.ts
```

## Don'ts (with the path forward)
- Don't treat email as identity → it is optional contact metadata only.
- Don't hand-roll auth → use the scaffolded passkey flows.
- Don't fetch ad hoc against the backend without going through the single-origin
  `/api/*` proxy (Caddy strips the prefix).
