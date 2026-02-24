# Screen Pattern Checklist

Use this checklist when building/refactoring app pages.

- [ ] **Header:** Use the shared sticky `PageHeader` with compact title scale (no page-local `text-2xl` top titles).
- [ ] **Page max-width:** Wrap content in a centered container (`mx-auto`) with an agreed max width (`max-w-3xl`/`max-w-5xl`) and standard horizontal padding (`px-4`).
- [ ] **Section spacing:** Prefer shared spacing tokens (`space-y-4`/`space-y-6`) and card sections over ad-hoc margins.
- [ ] **CTA style:** Use the shared `Button` variants (`primary`, `secondary`, `danger`, `ghost`) instead of page-local button classes.
- [ ] **Inputs:** Use shared `Input` for text-like fields where possible; keep custom controls (e.g., `select`, `textarea`, checkboxes) visually aligned with input tokens.
- [ ] **State coverage:** Each page should provide clear **empty**, **loading**, and **error** states using shared primitives (`Card`, `Alert`, helper text).
