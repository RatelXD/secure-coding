# 주거니 받거니 Design System

## 0. Research Log

- Concrete reference: inspected `C:\Users\jhou8\Downloads\stitch_.zip` screens `_1`–`_7` and its `warm_community_exchange/DESIGN.md`; this packet is the visual contract. Its remote fonts, logos, imagery, and URLs are not copied into this repository.
- Local implementation inputs: retained the permitted local Noto Sans KR variable font, brand logo, hero art, and `stitch-symbols.svg` sprite. No network asset is required at runtime.
- Skipped greenfield research lanes: this is an existing service with a supplied concrete reference, so separate brand/lazyweb/image generation research would dilute that contract.

## 1. Atmosphere & Identity

**Warm Community Exchange** is a calm, trustworthy neighborhood market: a cool mint-paper canvas, grounded deep-teal navigation, and one warm-coral action accent. It is deliberately practical rather than glossy. The signature is a thin, softly elevated 64px navigation rail that makes marketplace actions feel organized without becoming a dashboard.

## 2. Color

| Role | Token | Value | Use |
|---|---|---:|---|
| Canvas | `--color-surface` | `#f1fcf8` | Page background and header tint |
| Lowest surface | `--color-surface-lowest` | `#ffffff` | Cards, inputs, compact controls |
| Quiet surface | `--color-surface-low` | `#ebf6f2` | Quiet fills and hover wells |
| Active surface | `--color-surface-container` | `#e5f0ed` | Icon-button hover state |
| Primary ink | `--color-on-surface` | `#131d1c` | Main text |
| Muted ink | `--color-on-surface-muted` | `#3e4947` | Secondary labels and inactive navigation |
| Trust teal | `--color-primary` | `#005c55` | Brand, selected nav, links, focus outline |
| Teal hover | `--color-primary-hover` | `#004942` | Interactive hover/active |
| Community coral | `--color-secondary` | `#a9371e` | High-intent sign-up or product action only |
| Coral hover | `--color-secondary-hover` | `#d95438` | Coral action hover |
| Outline | `--color-outline-variant` | `#bdc9c6` | Structural rules and input edges |
| Error | `--color-error` | `#ba1a1a` | Errors/destructive feedback |

Use teal for navigation and focus, coral only for a high-intent action. Do not add gradients, neon, pure black, or remote visual assets.

## 3. Typography

- **Primary:** `"Noto Sans KR", system-ui, sans-serif` from the local WOFF2; it is the Korean-readable implementation substitute for the reference’s Plus Jakarta Sans / Be Vietnam Pro pairing.
- **Display:** 32px / 44px, 700, -0.01em.
- **Section heading:** 22px / 32px, 700, -0.01em.
- **Navigation/body:** 16px / 26px, 600 for navigation; body is 16px / 26px, 400.
- **Small label:** 12px / 18px, 700, 0.05em.

Body text never falls below 14px. Navigation labels remain single-line and may scroll as one keyboard-reachable row on narrow screens rather than shrinking into unreadable text.

## 4. Spacing & Layout

The base unit is 4px: `--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4` 16px, `--space-5` 20px, `--space-6` 24px, `--space-8` 32px, `--space-10` 40px, `--space-12` 48px. Desktop content is capped at 1440px with 40px page margins; mobile uses 16px content margins.

The shared header is a fixed three-region shell at desktop: brand, centered primary navigation, and trailing utility icons. It is 64px high. At 900px and below it becomes a compact brand/action rail plus a fixed 64px bottom navigation with home, search, raised product registration, chat, and MY actions. The document’s top and bottom padding follow these fixed rails; no primary content may sit underneath them. The header itself never scrolls, and document scroll remains the sole vertical scroll owner.

## 5. Components

### Shared site header

- **Structure:** `<header>` → brand link, primary `<nav><ul>`, utility icon cluster.
- **Variants:** anonymous (search, login, sign-up); authenticated (search, notification icon link, profile icon link). The account profile owns the CSRF-protected logout control.
- **Spacing:** 64px desktop rail; 12–20px utility gaps; 44px minimum interactive targets.
- **States:** teal selected nav underline; muted default; tonal hover well for icon utilities; visible teal focus ring; coral high-intent action; disabled is not used in the shell.
- **Accessibility:** named navigation landmark; each icon has a visually-hidden text name; normal link/button semantics and source-order keyboard navigation; active route uses `aria-current="page"`; logout is a real POST form with `{% csrf_token %}`.
- **Layout:** fixed header with document scroll ownership. The mobile navigation is a keyboard-reachable fixed bottom rail, including a raised product-registration action rather than a JS-only menu.
- **Motion:** 160ms color/background/shadow transition only; no animated layout.

### Navigation item

- **Structure:** list item containing one anchor.
- **States:** default, hover, current, focus-visible. Current state is communicated by both teal text and a 3px underline; it never relies on color alone.

### Utility icon action

- **Structure:** anchor or submit button containing local SVG `<use>` and an accessible name.
- **States:** 44px target, transparent default, mint hover well, 2px teal focus outline, 1px translate on active. It must not be represented by an emoji or remote icon font.

### Mobile bottom navigation

- **Structure:** a semantic `<nav>` with five same-origin links: home, search, product registration, chat, and MY.
- **States:** the current link receives the teal foreground; the product-registration link is a 56px coral circular action elevated 32px above the rail.
- **Accessibility:** all entries have text labels or an accessible name, remain ordinary anchors without JavaScript, and retain the global teal focus ring.

## 6. Motion & Interaction

Micro-interactions use 160ms `ease-out` transitions of color, background-color, box-shadow, and transform; active controls move at most 1px using `transform`. No width, height, position, or spacing animation is allowed. `prefers-reduced-motion: reduce` removes non-essential transition time and smooth scrolling.

## 7. Depth & Surface

This system uses **mixed tonal shift + restrained ambient shadow**. The mint canvas sits behind white controls; the fixed header has an outline-variant bottom rule, a translucent mint surface, and `--shadow-header` (a low-opacity teal shadow). Only interactive/elevated surfaces receive `--shadow-interactive`. Rounded corners are 4px, 8px, 12px, 16px, and pill; compact header icon buttons use the pill token.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

- Target WCAG 2.2 AA: 4.5:1 normal-text contrast and 3:1 large-text contrast.
- Every interactive target is at least 44px in one dimension, is keyboard reachable, and displays a 2px teal focus outline with a pale-teal offset ring; forced-colors mode keeps a system-color outline.
- Search has a programmatic label, SVG icons are decorative when paired with text labels, and landmark names are Korean.
- The responsive shell must have no horizontal document overflow at 390px; the navigation reel may scroll horizontally but stays fully keyboard reachable.
- Preserve normal browser form behavior with JavaScript unavailable. Respect reduced motion.

### Accepted Debt

| Item | Location | Why accepted | Owner / exit |
|---|---|---|---|
| Local type differs from the packet’s remote reference fonts | `src/static/fonts/NotoSansKR-Variable.woff2` | The supplied reference fonts are remote and cannot be copied; the licensed local Korean font is required for same-origin operation. | Replace only if an approved, locally licensed Korean-capable family is added. |
| The supplied mobile reference uses remote Material Symbols | `src/static/icons/stitch-symbols.svg` | Same-origin local SVG symbols provide the equivalent accessible controls without runtime remote font loading. | Replace only with an approved local icon font or expanded local sprite. |
