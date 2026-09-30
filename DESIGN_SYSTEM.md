# Design System — Flow

Aesthetic target: **warm editorial**, following the Claude design language. A tinted cream
canvas, serif display headlines at regular weight, a coral accent used scarcely, and dark
warm-ink surfaces for product chrome. Deliberately warm and humanist where most AI products
reach for cool blue and slate — the cream tint is the differentiator, so nothing in the system
is pure white or a cool gray.

Color, type, radius, shadow and motion are delivered entirely through the token layer in
[web/src/index.css](web/src/index.css); component code never names a hex value.

---

## 1. Palette and semantic mapping

Three ramps are declared as `--color-<ramp>-<step>` theme variables; semantic tokens alias
onto them.

| Ramp | Character | Semantic role |
| --- | --- | --- |
| **cream** | warm neutral, 50 (canvas) → 950 (ink) | **Backbone** — canvas, surfaces, borders, and the whole text scale |
| **coral** | warm muted orange-red | **Primary / brand** — CTAs, links, focus ring, brand accents |
| **ink** | warm near-black, 800–950 | **Dark product surfaces** — code chrome, featured tiers, dark mode |

The trinity is cream + coral + dark ink. There is no fourth *surface* tone.

### Surfaces separate by hairline, not by fill

`--color-surface` equals `--color-bg`. Cards read as regions bounded by a 1px
`--color-border` hairline rather than as lighter rectangles floating on a darker page. This
is the system's "color-block first, shadow rare" rule: depth comes from the cream-to-dark
contrast between bands, not from elevation. Shadows exist but stay faint and are rarely used.

### The five-vibe problem (deliberate, documented exception)

Spark's study needs five *mutually distinguishable* framing accents (calm, zoomies, silly,
challenge, science). The surface trinity admits no fourth tone, so the five resolve as
**content accents, never surfaces**: `--color-frame-*` plus a matching `-tint`. Each is
desaturated and warmed to sit on cream, and coral itself is deliberately withheld from the
set so the brand CTA stays scarce and unambiguous. This is the one place the system carries
more than three hues, and it is scoped to content markers.

### Semantic token resolution

| Token | Light | Dark | Notes |
| --- | --- | --- | --- |
| `primary` | `#b55839` | `coral-400` `#d28d74` | fill **and** link text — see §5 for why it is not `#cc785c` |
| `bg` / `surface` | `cream-50` `#faf9f5` | `ink-950` `#181715` | identical by design; cards use borders |
| `surface-2` / `-3` | `cream-100` / `cream-200` | `ink-800` | soft bands, card fills, inset areas |
| `surface-dark*` | `ink-950/900/800` | same | product chrome in **both** modes, not a dark-mode-only affordance |
| `text` | `cream-950` `#141413` | `cream-50` | warm dark, never pure black |
| `text-body` | `cream-800` `#3d3d3a` | `cream-100` | running paragraph text |
| `text-muted` | `cream-700` `#6c6a64` | `cream-500` | sub-headings, secondary labels |
| `text-subtle` | `cream-600` `#8e8b82` | `cream-600` | captions and placeholders — **UI/large only** |
| `border` | `cream-400` `#e6dfd8` | `#34312c` | one elevation step, not an ink line |
| `accent` | `#377e70` | `#7fcfc0` | teal companion, used sparingly |

---

## 2. Light & dark mode

Dark mode is **not** an inversion of a separate palette — it moves onto the same warm-ink
surfaces the light theme already uses for product chrome, so both modes share one vocabulary.
Coral holds its hue rather than shifting cool. The one structural flip is `on-primary`: white
on the deeper coral fill in light, near-black on the lighter coral fill in dark, so the label
stays legible either way.

---

## 3. Typography

The display/body split is the brand voice and is treated as unbreakable.

- **Display — serif, weight 400.** `--font-display` walks
  `"Tiempos Headline", "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua",
  Georgia, "Times New Roman", serif`. Copernicus and StyreneB are licensed Anthropic
  typefaces, and the app ships no web fonts (offline-friendly PWA), so the stack resolves to
  the closest widely-installed faces.
- **Body — humanist sans, weight 400/500.** Inter first, then the platform UI sans.
- **Negative tracking is mandatory on display sizes** (`--tracking-display-xl` … `-sm`,
  -1.5px → -0.3px). A serif headline without it reads as off-brand.
- **Display weight never exceeds 400.** For more emphasis, go up a size — never to bold.

### Type utilities

The four display steps are exposed as utilities (`display-xl` / `-lg` / `-md` / `-sm`) plus
`eyebrow` for uppercase captions. Each bundles family + size + weight + tracking, because
those four always travel together; exposing them as one class stops call sites re-deriving
the combination and drifting into bold sans headings.

---

## 4. Spacing, radius, shadow, motion

- **Spacing:** Tailwind's default 4px scale, unmodified.
- **Radius:** hierarchical, per the design language — `xs 4 / sm 6 / md 8 / lg 12 / xl 16 /
  pill 9999`. Controls take `md`, content cards `lg`, marquee containers `xl`.
- **Shadow:** faint and rare (`--shadow-xs` … `-lg`). Depth is carried by surface contrast.
- **Motion:** color and border transitions on interactive states; keyframe animation exists
  only in Spark's timer/mic/loader, gated behind `prefers-reduced-motion`.

---

## 5. Accessibility / WCAG contrast pass

Ratios computed against the **rendered** pairings, canvas `#faf9f5`. Targets: 4.5:1 normal
text, 3:1 large text / UI.

| Pairing (light) | Ratio | Result |
| --- | --- | --- |
| `text` `#141413` on canvas | 17.50 | ✅ AAA |
| `text-body` `#3d3d3a` on canvas | 10.34 | ✅ AAA |
| `text-muted` `#6c6a64` on canvas | 5.13 | ✅ AA |
| `text-subtle` `#8e8b82` on canvas | 3.23 | ✅ large/UI only (intended use) |
| white on `primary` `#b55839` | 4.75 | ✅ AA |
| `primary` as link text on canvas | 4.51 | ✅ AA |
| white on `primary-hover` `#a9583e` | 5.06 | ✅ AA |
| `accent` `#377e70` on canvas | 4.55 | ✅ AA |
| `success` `#3d804d` on canvas | 4.54 | ✅ AA |
| `warning` `#956c0c` on canvas | 4.50 | ✅ AA |
| `danger` `#c64545` on canvas | 4.59 | ✅ AA |
| white on `danger` | 4.84 | ✅ AA |
| `frame-calm` `#3f7e70` | 4.50 | ✅ AA |
| `frame-zoomies` `#a46424` | 4.50 | ✅ AA |
| `frame-silly` `#b2537a` | 4.52 | ✅ AA |
| `frame-challenge` `#a04a3c` | 5.63 | ✅ AA |
| `frame-science` `#5a6f9c` | 4.76 | ✅ AA |
| white on each `frame-*` (rank badges) | 4.74 – 5.93 | ✅ AA |

### Deviation from the source design language

The Claude design language specifies `button-primary` as **white on coral `#cc785c`**. That
pairing measures **3.28:1** — it fails AA for the 14px/500 label the same spec puts on it.
Coral as inline link text on cream measures **3.11:1** and fails likewise.

Resolution: `--color-primary` is set one lightness step deeper at **`#b55839`**, holding hue
and saturation constant so the coral character is unchanged. The literal brand value survives
as `--color-coral-brand` and is used only where nothing sits on it — the focus ring and
decorative tints. The companion teal, success, warning and three of the five vibe accents were
darkened the same way, by lightness only.

This is a deliberate, documented departure: on a platform whose participants include people we
cannot screen for vision, a brand hex is not worth a failing contrast ratio.

---

## 6. Components & anti-duplication

One canonical implementation per primitive (see [COMPONENT_AUDIT.md](COMPONENT_AUDIT.md) and
[COMPONENT_MAP.md](COMPONENT_MAP.md)). Notable decisions:

- **`Badge` vs `Chip` split by interactivity, not appearance.** `Badge` is a read-only
  `<span>` for status; `Chip` is a real `<button>` with `aria-pressed` for anything
  selectable. Because the split is semantic, neither can absorb the other — which is what had
  previously let Spark grow its own `.spark-chip`.
- **`ChipGroup` owns single-select.** Generic in the option type, so a group over
  `SparkFrame` cannot be handed a stray string. Layout is a *second axis*: `wrap` renders an
  inline pill row, `stack` a full-width option list. Omitting `value` makes it an action
  group. One component answers "pick one from a closed set" in every presentation.
- **`ScaleControl`** is the single anchored 1–N rating instrument. It was previously
  hand-rolled twice — a local helper in `CueStep` and inline markup in `ReflectStep` — which
  let two renderings of the same research instrument drift apart.
- **`SectionHeader`** covers both the icon-led form (Admin, Settings) and the eyebrow-led
  editorial form (Spark flow steps); they are the same thing, a titled section boundary.
- **`Card` with `onClick` renders a `<button>`**, not a clickable `<div>`, so the interactive
  form is focusable and Enter/Space-activated by construction.
- **`framingOf()`** resolves an untrusted frame string to a framing definition in one place.
  The `FRAMINGS[x] ?? FRAMINGS.calm` partial-index-plus-ad-hoc-default had been re-typed in
  four files.
- **No Spark styling exception.** `spark.css` previously held 528 lines scoped under
  `.spark-zone`, including its own palette and a shim aliasing `--color-*` to bare names. It
  is now ~150 lines of keyframe animation, which is the one thing utilities cannot express.
- All status color lives behind `success` / `warning` / `danger` / `info` / `primary` tokens.
  No raw Tailwind palette classes (`yellow-500`, `blue-100`, `gray-500`, …) and no inline
  `style={{ color: … }}` remain in component code.
