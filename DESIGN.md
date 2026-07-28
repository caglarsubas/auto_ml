# Design System — declar.ai

## Product Context
- **What this is:** End-to-end declarative AutoML platform for tabular model development, with a guided CRISP-DM / pipeline workbench.
- **Who it's for:** Data scientists and model validation teams building credit scoring, risk, and other regulated models.
- **Space/industry:** AutoML / credit risk / model governance (peers: DataRobot, H2O Driverless AI, Dataiku, scorecard studios).
- **Project type:** Dense web app / internal-grade workbench (Angular + Material), not a marketing site.

## Memorable thing
Serious, auditable software for regulated model work — every decision is **declared**, not magic.

## Aesthetic Direction
- **Direction:** Industrial / Utilitarian
- **Decoration level:** Minimal — borders, type, and stage state carry hierarchy; no decorative blobs, icon-circle grids, or automation theater
- **Mood:** Calm, dense, institutional. Validator-ready. Brand wine signals seriousness; amber is rare attention, not decoration.
- **Reference sites:** DataRobot / H2O / Dataiku (category literacy); scorecard workbenches (audit & stage clarity). Differentiator: declared human governance vs “we ran hundreds of models for you.”

## Typography
- **Display/Hero:** IBM Plex Sans (Semibold/Bold) — brand and page titles
- **Body:** IBM Plex Sans — readable UI copy
- **UI/Labels:** IBM Plex Sans Medium/Semibold — form labels, nav, stage names
- **Data/Tables:** IBM Plex Mono with `font-variant-numeric: tabular-nums` — metrics, IDs, numeric columns
- **Code:** IBM Plex Mono
- **Loading:** Google Fonts — `IBM+Plex+Sans` and `IBM+Plex+Mono` with `display=swap`; preconnect to fonts.googleapis.com / fonts.gstatic.com
- **Do not use as primary:** Inter, Roboto, Arial, system-ui stacks, Space Grotesk, indigo/purple display treatments
- **Scale:**
  - xs: 0.75rem / 12px
  - sm: 0.875rem / 14px
  - base: 1rem / 16px (minimum body)
  - lg: 1.125rem / 18px
  - xl: 1.25rem / 20px
  - 2xl: 1.5rem / 24px
  - 3xl: 1.875rem / 30px
  - 4xl: 2.25rem / 36px

## Color
- **Approach:** Restrained — one brand primary, one sparse accent, cool neutrals, semantic statuses
- **Primary:** `#740505` — brand maroon (toolbar, primary CTAs, active brand text). Scale through `--primary-50` … `--primary-950` with `--primary-700: #740505`
- **Secondary / Accent:** `#b45309` — warm amber for rare highlights, progress cues, warnings adjacency. Never as full-page purple/indigo gradients
- **Neutrals:** Cool zinc `#fafafa` → `#18181b` (`--neutral-50` … `--neutral-900`)
- **Semantic:** success `#059669`, warning `#d97706`, error `#dc2626`, info `#2563eb`
- **Dark mode:** Prefer surface elevation (darker panels) over pure inversion; keep text off-white (~`#e4e4e7`); desaturate accent ~10–20%

### Token map (CSS)
```css
--primary-700: #740505;
--accent-600: #b45309;
--neutral-50: #fafafa;
--neutral-800: #27272a;
--toolbar-height: 72px;
--font-sans: 'IBM Plex Sans', 'Segoe UI', sans-serif;
--font-mono: 'IBM Plex Mono', Menlo, Consolas, monospace;
```

## Spacing
- **Base unit:** 8px
- **Density:** Comfortable-compact (workbench-first)
- **Scale:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64) — prefer `--space-*` tokens in `frontend/src/styles.css`

## Layout
- **Approach:** Grid-disciplined hybrid — strict columns in the app; login may use a centered card
- **Shell:** Sticky burgundy toolbar (`--toolbar-height`); optional left pipeline / stage rail; main workspace
- **Grid:** Fluid content with max width ~1200–1280px on home/marketing-like views; workbench may go full width
- **Border radius:** sm 4px · md 6–8px · lg 8–12px · avoid uniform large “bubbly” radius on every control
- **Cards:** Only when the card *is* the interaction (e.g. navigable home sections). No decorative card mosaics in the hero or pipeline chrome

## Motion
- **Approach:** Minimal-functional
- **Easing:** enter ease-out · exit ease-in · move ease-in-out
- **Duration:** micro 50–100ms · short 150–250ms · medium 250–400ms
- **Rules:** No logo magnifiers or ornamental hover theater; respect `prefers-reduced-motion`; prefer animating `opacity` / `transform` only; avoid `transition: all`

## Interaction & a11y baseline
- Visible `focus-visible` rings (maroon/primary), never `outline: none` without a replacement
- Touch targets ≥ 44px where practical on primary actions
- Errors: specific message + `role="alert"` / `aria-live` when dynamic
- Login must not show authenticated app nav or Sign Out
- Preserve visited vs unvisited link distinction outside toolbar chrome

## Anti-patterns (do not ship)
- Purple / indigo gradient themes or blue-to-purple schemes
- 3-column icon-in-circle feature grids
- Centered-everything marketing layouts inside the workbench
- Happy talk (“Welcome to…”, “Democratizing…”, “Unlock the power…”)
- Placeholder-as-only-label on forms
- Scattered raw brand hex when a token exists — use `var(--primary-700)` (charts may keep explicit series colors)

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-28 | Initial design system created | `/design-consultation` — Industrial/Utilitarian, wine+amber, IBM Plex; memorable thing: declared, not magic |
| 2026-07-28 | Preview via HTML (AI mockups unavailable) | OpenAI design generate failed (rate limit/socket); HTML preview approved |
| 2026-07-28 | Outside voices skipped | User chose speed; research + thesis already clear |
| 2026-07-28 | Applied tokens to live frontend on v3.1.0 | `styles.css` / shell / login / home aligned to this doc |
| 2026-07-28 | Workbench token pass + `wb-*` helpers | Modeling/model-dev/pipeline/ai-chat hex → tokens; CRISP nav as buttons; drop teal third-brand |
