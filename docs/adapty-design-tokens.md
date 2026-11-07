# Adapty dashboard: stack and design tokens

Captured from app.adapty.io on 7 Nov 2026 for a possible later UI (not part of the MVP). Kept so nobody has to re-measure.

**Stack.** React SPA built with Vite (hashed chunks, CSS Modules named `_Name_hash`), TanStack Query, zustand, Sentry.

**Fonts.** Inter for body (14px/20px, weight 400; captions 12px/16px), Inter Tight for titles (`--a-text-title` 20px/28px weight 600; `--a-text-display-1` 24px/32px). Both on Google Fonts.

**Colours** (CSS variables on `:root`):

| Token | Value | Use |
|---|---|---|
| `--blackPrimary` | `#111` | text |
| `--black-600` | `#696969` | secondary text |
| `--purplePrimary` / `--purpleSecondary` | `#6720ff` / `#7e41ff` | primary button, hover |
| `--softBackground` / `--neutralBackground` | `#f8f4ff` / `#faf9fc` | soft panels |
| `--borderColor` (`--black-100`) | `#e7e7e7` | card and table borders |
| `--bgHover` (`--black-50`) | `#f3f3f3` | hover rows, selected menu item |
| `--green-400` / `--green-50` | `#1ea672` / `#f2faf5` | Live dot, positive |
| `--yellow-400` / `--yellow-50` | `#eeae40` / `#faf7ed` | warning |
| `--red-400` / `--red-50` | `#d74247` / `#fcedef` | error |
| `--blue-400` / `--blue-50` | `#4777ff` / `#f2f7ff` | info |

**Geometry.** Spacing base 4px (`--a-spacing-*`), buttons radius 8px, menu items 6px, cards 1px border and ~12px radius, content width 960px, left sidebar 240px white with a 1px inset border.

**Patterns on the A/B test page.** Breadcrumb «← A/B tests / test name»; action row (View in analytics, Duplicate, Modify, Stop); status card (Status · Live with a green dot, Started at, Duration, Placement); arm rows with a coloured checkbox (B purple, A orange) and a «50%» weight pill; columns P2BB and Predicted P2BB («insufficient data» until ~2 weeks).
