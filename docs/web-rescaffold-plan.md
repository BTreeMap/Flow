# Web Rescaffold Migration Plan

## Flow-required frontend routes and features

- [x] `/` landing page
- [x] `/register` passkey registration
- [x] `/login` passkey login
- [x] `/dashboard` project thread list (active + ended visible)
- [x] `/p/:projectId/activate` invite claim + optional email
- [x] `/p/:projectId/chat` POST + SSE chat
- [x] `/p/:projectId/notifications` Web Push onboarding/subscription
- [x] `/settings` passkey list + rename + revoke

## Non-negotiable constraints

- Caddy strips `/api` prefix before proxying to backend.
- `VITE_API_BASE_URL` defaults to `/api` for web app requests.
- PWA manifest and service worker must remain present.
- Chat must use SSE with reconnect and dedupe.
- Push flow must use project-scoped endpoints:
  - `/p/{project_id}/push/vapid-public-key`
  - `/p/{project_id}/push/subscribe`
  - `/p/{project_id}/push/unsubscribe`

## Current Flow-specific assets/config inventory

- `web/public/manifest.json`
- `web/public/sw.js`
- `web/vite.config.ts` (`/api` proxy rewrite)
- `web/e2e/*.spec.ts` Playwright coverage
- Flow product pages in `web/src/pages/*`

## Upstream scaffold vs Flow-specific file classes

| Class | Files |
|---|---|
| Keep from upstream scaffold | `web/src/api/client.ts`, `web/src/api/types.ts`, `web/src/pages/Settings.tsx`, `web/src/pages/Settings.test.tsx` |
| Flow-specific migrated | `web/src/App.tsx`, `web/src/components/Layout.tsx`, `web/src/pages/Landing.tsx`, `web/src/pages/Login.tsx`, `web/src/pages/Register.tsx`, `web/src/pages/Dashboard.tsx`, `web/src/pages/Activation.tsx`, `web/src/pages/ChatThread.tsx`, `web/src/pages/Notifications.tsx` |
| Deployment/PWA migrated | `web/.dockerignore`, `web/Caddyfile`, `web/Dockerfile`, `web/public/manifest.json`, `web/public/sw.js`, `web/vite.config.ts` |
| Test surface migrated | `web/e2e/*.ts` (including passkey rename coverage) |

## Migration tracker (old web -> temp scaffold)

| Status | Source path | Destination path | Notes | Validation |
|---|---|---|---|---|
| [x] | `web/src/App.tsx` | `.tmp/h4ckath0n-web/src/App.tsx` | Route map + guards | `npm run typecheck` |
| [x] | `web/src/components/Layout.tsx` | `.tmp/h4ckath0n-web/src/components/Layout.tsx` | Nav links + auth actions | `npm run lint` |
| [x] | `web/src/pages/Landing.tsx` | `.tmp/h4ckath0n-web/src/pages/Landing.tsx` | Flow messaging only | Manual route snapshot |
| [x] | `web/src/pages/Register.tsx` | `.tmp/h4ckath0n-web/src/pages/Register.tsx` | Passkey register flow | Existing Playwright passkey path |
| [x] | `web/src/pages/Login.tsx` | `.tmp/h4ckath0n-web/src/pages/Login.tsx` | Passkey login flow | Existing Playwright passkey path |
| [x] | `web/src/pages/Dashboard.tsx` | `.tmp/h4ckath0n-web/src/pages/Dashboard.tsx` | Membership thread list | `npm run typecheck` |
| [x] | `web/src/pages/Activation.tsx` | `.tmp/h4ckath0n-web/src/pages/Activation.tsx` | Invite claim | `npm run typecheck` |
| [x] | `web/src/pages/ChatThread.tsx` | `.tmp/h4ckath0n-web/src/pages/ChatThread.tsx` | SSE reconnect + dedupe | `npm run typecheck` |
| [x] | `web/src/pages/Notifications.tsx` | `.tmp/h4ckath0n-web/src/pages/Notifications.tsx` | iOS guidance + push | `npm run typecheck` |
| [x] | `web/src/pages/Settings.tsx` | `.tmp/h4ckath0n-web/src/pages/Settings.tsx` | Keep upstream name-based rename implementation | `vitest src/pages/Settings.test.tsx` |
| [x] | `web/src/auth/*` | `.tmp/h4ckath0n-web/src/auth/*` | Scaffold auth integration + Flow auth API tweaks | `npm run test` |
| [x] | `web/src/api/*` | `.tmp/h4ckath0n-web/src/api/*` | OpenAPI-generated client/types + path assertions | `npm run lint` |
| [x] | `web/public/manifest.json` | `.tmp/h4ckath0n-web/public/manifest.json` | PWA manifest | Manual file check |
| [x] | `web/public/sw.js` | `.tmp/h4ckath0n-web/public/sw.js` | Push + click handling | Manual file check |
| [x] | `web/vite.config.ts` | `.tmp/h4ckath0n-web/vite.config.ts` | `/api` proxy rewrite | `npm run dev` startup |
| [x] | `web/e2e/*` | `.tmp/h4ckath0n-web/e2e/*` | Preserve + adapt tests (rename selectors updated) | CI failure repro addressed |
