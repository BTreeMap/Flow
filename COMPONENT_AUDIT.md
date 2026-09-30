# Component Audit — Flow `web/` frontend

> Phase 0 discovery. **No code changed yet.** This audit is the input to the design-system
> and migration work in later phases. Read the "Near-duplicate flags" and "Non-token color
> usage" sections before writing any implementation code.

## 1. Stack

| Concern | Finding |
| --- | --- |
| Framework | **React 19** (`react@^19.1`, `react-dom@^19.1`) |
| Router | `react-router@^7.12` (data routes in [web/src/App.tsx](web/src/App.tsx)) |
| Build tool | **Vite 7** (`vite@^7`, `@vitejs/plugin-react`) |
| Language | TypeScript ~5.9, strict project refs (`tsc -b`) |
| Styling | **Tailwind CSS v4** via `@tailwindcss/vite` — confirmed v4 by the `@theme { … }` block in [web/src/index.css](web/src/index.css) and the absence of any `tailwind.config.{js,ts}`. No CSS modules, no styled-components, no SASS. A handful of inline `style={{…}}` props exist only for dynamic viewport / safe-area math, not color. |
| Icons | `lucide-react` |
| Markdown | `streamdown` (assistant message rendering) |
| Tests | Vitest + Testing Library (unit), Playwright (e2e) |

**Conclusion:** Tailwind v4 is already installed and configured correctly. This is a
**re-theme of an existing, already-tokenized design system**, not a from-scratch Tailwind
introduction. The bulk of the work is (a) repointing the semantic token layer to the new
palette, (b) adding the raw 5-scale palette as theme variables, (c) eliminating the small
number of non-token color usages, and (d) consolidating the inline "pill/badge" pattern.

## 2. Tailwind status

- **Version: v4.** Tokens are declared in a single `@theme` block in
  [web/src/index.css](web/src/index.css#L4) and dark mode is handled by overriding the same
  custom properties under `html[data-theme="dark"]` ([web/src/index.css](web/src/index.css#L96)).
- Theme switching is real and wired: an inline boot script in [web/index.html](web/index.html#L5)
  sets `data-theme` before paint; [web/src/theme.ts](web/src/theme.ts) + the nav in
  [web/src/components/Layout.tsx](web/src/components/Layout.tsx) toggle `light`/`dark`/`system`.
- **Existing semantic tokens** (already consumed across the app): `primary`, `primary-hover`,
  `primary-dark`, `on-primary`, `bg`, `surface`, `surface-2/3/alt/muted/hover`, `text`,
  `text-muted`, `text-subtle`, `border`, `divider`, `success`, `warning`, `danger`,
  `danger-hover`, `error`, plus chat tokens `chat-bg`, `bubble-in/out/system`, `focus`, and
  non-color tokens for radius/shadow/layout.
- **There is no raw color scale** (no `--color-primary-500` family); only semantic aliases
  exist today. The new palette ships as full 50–950 scales, so Phase 2 will add the raw
  scales *and* keep the semantic alias layer on top.

## 3. Full component inventory

### Primitives — `web/src/components/`
| File | Component(s) | Visual purpose | Props |
| --- | --- | --- | --- |
| [Button.tsx](web/src/components/Button.tsx) | `Button` | Text button | `variant: primary\|secondary\|danger\|ghost`, `size: sm\|md\|lg`, native button attrs |
| [Card.tsx](web/src/components/Card.tsx) | `Card`, `CardHeader`, `CardContent` | Surface container w/ optional header & body | `children`, `className`, `onClick` |
| [Input.tsx](web/src/components/Input.tsx) | `Input` | Labeled text field w/ error | `label`, `error`, native input attrs |
| [Alert.tsx](web/src/components/Alert.tsx) | `Alert` | Inline status banner w/ icon | `variant: info\|success\|warning\|error`, `children` |
| [SectionHeader.tsx](web/src/components/SectionHeader.tsx) | `SectionHeader` | Icon + title + subtitle + action row | `icon`, `title`, `subtitle`, `action` |
| [ProtectedRoute.tsx](web/src/components/ProtectedRoute.tsx) | `ProtectedRoute` | Auth/role route guard (renders a loading state) | `children`, `requiredRole` |
| [NotificationBanner.tsx](web/src/components/NotificationBanner.tsx) | `NotificationBanner` | Push-enable / push-blocked banner | none (reads route + hook) |

### Mobile-first UI primitives — `web/src/components/ui/`
| File | Component | Visual purpose | Props |
| --- | --- | --- | --- |
| [IconButton.tsx](web/src/components/ui/IconButton.tsx) | `IconButton` | Circular 44px icon-only button | `children`, `label`, native attrs |
| [PageHeader.tsx](web/src/components/ui/PageHeader.tsx) | `PageHeader` | Sticky page title bar + actions | `title`, `actions` |
| [ListRow.tsx](web/src/components/ui/ListRow.tsx) | `ListRow` | Tappable list row (avatar/primary/secondary/trailing/unread) | `avatar`, `primary`, `secondary`, `trailing`, `unread`, `onClick` |
| [BottomNav.tsx](web/src/components/ui/BottomNav.tsx) | `BottomNav` | Bottom tab bar (portrait) | none (internal `navItems`) |
| [ChatHeader.tsx](web/src/components/ui/ChatHeader.tsx) | `ChatHeader` | Chat top bar: back, title, connection status pill, kebab menu, debug toggle | `title`, `avatar`, `backTo`, `hideBack`, `connectionStatus`, `menuItems`, `debugMode`, `onToggleDebug` |
| [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx) | `MessageBubble` | Chat bubble (user/assistant/system) + debug panel + condition pill | `role`, `content`, `metadata`, `timestamp`, `isGroupContinuation`, `isStreaming`, `debugInfo`, `showDebug` |
| [Composer.tsx](web/src/components/ui/Composer.tsx) | `Composer` | Auto-growing message input + send | `onSend`, `disabled` |

### Shells / layout — `web/src/components/` and `web/src/components/shell/`
| File | Component | Visual purpose |
| --- | --- | --- |
| [Layout.tsx](web/src/components/Layout.tsx) | `Layout` | Top-nav chrome for public/auth pages (landing, login, register, admin, activation, onboarding) incl. theme toggle + mobile hamburger |
| [MobileShell.tsx](web/src/components/MobileShell.tsx) | `MobileShell` | Portrait app shell: scroll area + `BottomNav` |
| [ChatShell.tsx](web/src/components/ChatShell.tsx) | `ChatShell` | Portrait immersive chat shell (no nav) + `NotificationBanner` |
| [shell/AppShell.tsx](web/src/components/shell/AppShell.tsx) | `AppShell` | **Responsive switch**: `MobileShell` (bottom) ↔ `SideRailShell` |
| [shell/ChatAppShell.tsx](web/src/components/shell/ChatAppShell.tsx) | `ChatAppShell` | **Responsive switch**: `ChatShell` (bottom) ↔ `ChatShellSide` |
| [shell/SideRailShell.tsx](web/src/components/shell/SideRailShell.tsx) | `SideRailShell` | Desktop/landscape: `NavRail` + optional chat-list pane + main |
| [shell/ChatShellSide.tsx](web/src/components/shell/ChatShellSide.tsx) | `ChatShellSide` | Desktop chat: `NavRail` + chat-list pane + thread |
| [shell/NavRail.tsx](web/src/components/shell/NavRail.tsx) | `NavRail` | Vertical 72px nav rail (desktop) |

### Feature / composed components
| File | Component | Visual purpose |
| --- | --- | --- |
| [chat/AssistantMarkdown.tsx](web/src/components/chat/AssistantMarkdown.tsx) | `AssistantMarkdown` | Streamdown markdown renderer w/ prose tweaks |
| [chat/FeedbackPollWidget.tsx](web/src/components/chat/FeedbackPollWidget.tsx) | `FeedbackPollWidget` | In-bubble feedback poll |
| [chats/ChatListPane.tsx](web/src/components/chats/ChatListPane.tsx) | `ChatListPane` | Project/thread list (used standalone on mobile + embedded in desktop rail shells) |

### Pages — `web/src/pages/`
`Landing`, `Login`, `Register`, `Activation`, `Onboarding`, `OnboardingNotifications`,
`Dashboard`, `ChatThread`, `Updates`, `UpdatesPage`, `Notifications`, `Settings`, `Admin`.
All consume the primitives above; none define their own button/card/input variants except
the inline status-pill / form-control patterns noted below.

## 4. Near-duplicate flags (read before Phase 3)

1. **Badge / pill / chip — implemented inline in ≥4 places, no canonical component.**
   - Condition pills `A/B/C/D` in [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx#L5)
   - Connection-status pill (`online/reconnecting/offline`) in [ChatHeader.tsx](web/src/components/ui/ChatHeader.tsx#L19)
   - Membership-status pill (`active/paused/ended`) + health-check pill in [Admin.tsx](web/src/pages/Admin.tsx#L539)
   - Unread dot in [ListRow.tsx](web/src/components/ui/ListRow.tsx#L48) and [BottomNav]/Dashboard
   - **Action:** introduce ONE `Badge` primitive with `variant` + optional `dot`, migrate all four. This is the single clearest consolidation win.

2. **Navigation item list duplicated.** [BottomNav.tsx](web/src/components/ui/BottomNav.tsx#L13)
   and [NavRail.tsx](web/src/components/shell/NavRail.tsx#L18) each hand-maintain their own
   `navItems` array (same routes, icons, labels; NavRail adds Admin). The two *renderers* are
   legitimately different (horizontal tabs vs vertical rail), but the **data** should be a
   single shared config to prevent drift. Not a component merge — a data-extraction.

3. **Header-ish components ×3.** [PageHeader.tsx](web/src/components/ui/PageHeader.tsx),
   [ChatHeader.tsx](web/src/components/ui/ChatHeader.tsx) and the top nav inside
   [Layout.tsx](web/src/components/Layout.tsx) are all sticky top bars. They serve genuinely
   different roles (simple page title vs interactive chat bar vs app-wide nav), so this is
   **kept-as-is** — flagged here only so it is a conscious decision, not an accident.

4. **Seven shell files look duplicative but are intentional.** `AppShell`/`ChatAppShell`
   are responsive routers that pick between a portrait shell (`MobileShell`/`ChatShell`) and
   a desktop shell (`SideRailShell`/`ChatShellSide`). This is a deliberate responsive
   architecture, **not** copy-paste duplication. `NotificationBanner` is rendered by both the
   portrait (`ChatShell`) and desktop (`ChatShellSide`) chat shells — consistent, fine. No
   consolidation needed; documented so a later reader doesn't "clean it up" by mistake.

5. **No competing Button/Card/Input/Modal implementations.** There is exactly one of each.
   `Button` is already variant-driven (4 variants × 3 sizes). There is **no** `PrimaryButton`,
   `ButtonV2`, second card, or second modal. The codebase is in good shape on this axis.

## 5. Non-token color usage (must be fixed during migration)

These are the only places that bypass the semantic token layer and hardcode Tailwind default
palette values or undefined tokens. Every one of these gets routed through a token in Phase 3.

| Location | Offending classes | Problem |
| --- | --- | --- |
| [Alert.tsx](web/src/components/Alert.tsx#L21) | `bg-yellow-500/10 text-yellow-600 border-yellow-500/20` | `warning` variant uses raw Tailwind yellow instead of the `warning` token. (Note: [Alert.test.tsx](web/src/components/Alert.test.tsx#L28) asserts these exact classes — test must be updated alongside.) |
| [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx#L5) | `bg-blue-100 text-blue-800`, `bg-purple-100 …`, `bg-amber-100 …`, `bg-emerald-100 …` | Condition pills hardcode 4 raw palettes. Should map onto palette/Badge variants. |
| [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx#L126) | `bg-muted` | **Undefined token** — there is no `--color-muted`; renders nothing. Bug surfaced by audit. |
| [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx#L164) | `text-red-500` | Debug error text hardcodes red; should be `text-danger`. |
| [UpdatesPage.tsx](web/src/pages/UpdatesPage.tsx#L33) | `text-gray-500` | Empty-state text hardcodes gray; should be `text-text-muted`. |
| [manifest.json](web/public/manifest.json#L8) | `theme_color: #f2f3f5` | PWA theme color hardcoded to the old neutral bg; must track the new palette's surface/bg. |
| [index.html](web/index.html#L33) | `meta theme-color #f2f3f5` | Same as above for the browser chrome color. |

Everything else in the app already uses semantic token classes (`bg-surface`, `text-text`,
`text-text-muted`, `bg-primary`, `border-border`, `bg-success/10`, `bg-danger/10`, …), so the
re-theme propagates automatically once the token values in `index.css` are repointed.

## 6. Proposed canonical structure (for Phase 1 sign-off)

- Keep the existing split: **primitives** in `components/` + `components/ui/`, **shells** in
  `components/shell/`, **feature** components in `components/chat/` & `components/chats/`. It
  already approximates a primitives-vs-composed convention; we will formalize it in the
  design-system doc rather than reshuffle folders (low risk, no call-site churn).
- **Add one primitive:** `Badge` (consolidates flag #1).
- **Extract one config:** shared `navItems` consumed by both `BottomNav` and `NavRail` (flag #2).
- No other new components anticipated.

---

### Stop / review gate

This completes Phase 0. Per the task protocol, no styles or colors have been migrated yet.
Pending review of this audit, Phase 1 will produce `DESIGN_SYSTEM.md` (semantic token mapping
of the five scales, light/dark resolution, type scale, and a WCAG contrast pass) before any
implementation.
