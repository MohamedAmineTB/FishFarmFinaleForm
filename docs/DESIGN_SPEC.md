# FishFarm: design specification

The approved design is the clickable prototype in **`docs/design-reference.html`**. It is
the single source of truth for how the app looks and behaves. The screenshots in
**`docs/screenshots/`** show every page and state. This document explains both so you
can rebuild them **exactly** in React.

> **About the screenshots:** they were captured offline, so the web fonts did not load and a
> fallback font shows. Animations did not run either (pages show their final resting state).
> For fonts, follow section 2 of this file. For everything else (layout, colours, spacing,
> sizes, content), match the screenshots.

## 0. Golden rules

1. **Port, don't redesign.** Copy the prototype's CSS, SVG paths, icons, canvas drawing code
   and text into the React app. Do not "improve", restyle or swap components for a UI library.
2. **No Tailwind, no component library.** Use the prototype's own CSS (moved into
   `frontend/src/styles/`, split by area, class names unchanged).
3. **Charts are hand-drawn SVG**, ported from the prototype's `lineChart`, `barChart`, `spark`
   and `gauge` functions into React components. Do not use Recharts or Chart.js.
4. **Same libraries, same versions:** GSAP 3.12.5 with ScrollTrigger, Lenis 1.1.13
   (install from npm, pinned). Fonts from Google Fonts (section 2).
5. **Every text string** in the prototype is final copy. Reuse it word for word.
6. **Data is real.** Everything the prototype simulates in the browser (`S` object, `tick()`,
   template answers) must come from the FastAPI back end in the real app (see BUILD_PROMPT.md).

## 1. Where things are in `design-reference.html`

| Part | Where to find it in the file |
|---|---|
| Design tokens | `:root{…}` at the top of `<style>` |
| Website (landing) styles | from `/* shared */` to `/* ============ DEMO APP ============ */` |
| App shell, tiles, badges, tables, forms, modal, toast, assistant panel | `/* ============ DEMO APP ============ */` block |
| Sign-in pages | `/* ============ AUTH ============ */` |
| App extras (topbar, bell, gauges, tank, sheet) | `/* ============ APP SHELL EXTRAS ============ */` |
| Home screens | `/* ============ HOME SCREENS … */` then `/* ============ v4 … */` (**v4 rules win**: light floating sidebar, simpler home, check-offs, read buttons) |
| Responsive rules | `/* responsive */` and the `@media` blocks inside each section |
| Canvas animations | JS section `/* ================= CANVAS SCENES` (`makeWater`, `drawFish`, stats water, night lake) |
| Charts | JS section `/* ================= CHARTS` (`lineChart`, `spark`, `barChart`, `basinChart`) + `gauge()` and `tank()` in the views section |
| Pages | JS `const views = { overview, ops, bench, basins, basin, alerts, reports, team, shift, sensors, maintenance, none }` |
| Sign-in logic | JS `/* ================= SIGN-IN PAGES` |
| Routing | JS `/* ================= ROUTING` |
| Assistant UI | JS `/* ================= ASSISTANT` |
| Website motion | JS `/* ================= LANDING PAGE MOTION` |

## 2. Design tokens

```css
--ink:#0c1d22;      /* text */
--deep:#0f3a42;     /* primary buttons, active nav, dark panels */
--current:#1d6f6a;  /* teal accent, links, chart lines */
--reed:#8dbb63;     /* third step colour */
--aqua:#cfe8e1;     /* ticket cards, pills, footer */
--foam:#eef6f3;     /* soft surfaces, hover */
--line:#e2ebe7;     /* borders */
--paper:#ffffff;
--bg:#e4efeb;       /* page behind the website */
--muted:#4f6268;    /* secondary text */
--ok:#2e9b6f; --warn:#d98a1c; --crit:#d6453d;   /* status */
--radius:22px;
```
App background: `#eef5f2`. Semantic colours are for status only, never decoration.

**Fonts** (Google Fonts, one stylesheet link):
`Bricolage Grotesque` (opsz 12..96, weight 300–700) for display/headings,
`Geist` (400/500/600) for body, `Geist Mono` (400/500) for numbers, times, readings, codes.
Headings use `letter-spacing:-.03em` to `-.05em`, `text-wrap:balance`.
Numbers use `font-variant-numeric: tabular-nums`.

**Signature details to keep:**
- Wavy teal underline on the emphasised words of big headlines (`text-decoration: underline wavy`), applied per word span.
- Ticket cards with semicircle notches on both sides (CSS `mask` with two radial gradients).
- Frosted glass reading chips (`backdrop-filter: blur(12px)`), with a pinging green dot.
- Giant step numerals 1/2/3 in deep / current / reed.

## 3. Components (class names from the prototype)

| Component | Classes | Notes |
|---|---|---|
| Primary / ghost button | `.btn`, `.btn.ghost`, `.btn.wide` | pill, 38px high, hover lifts 1px |
| Small button | `.small-btn`, `.primary`, `.ok`, `.glassy`, `.danger` | 30px pill |
| Pill label | `.pill` (+ `<i>` green dot) | section eyebrows |
| Badge | `.badge .b-healthy/.b-warning/.b-critical/.b-info/.b-est` | dot + text |
| Tile | `.tile`, `.tile .k` label, `.tile .v` value | white card, 16px radius, 1px line shadow |
| Ticket card | `.card` inside `.tickets` | notched aqua card; alert variant `.alert-card` (pink) |
| Basin tank | `.tank` + `.water` + `.wv` SVG waves + `.tank-fish` | water height = O₂ saturation × 0.85 (clamped 18–92%); colour by status |
| Gauge | `gauge(b,m)` SVG | semicircle, safe band light teal, amber/red bands for oxygen, marker coloured by status |
| Line chart | `lineChart()` | 640×220 viewBox, 4 grid lines, area gradient, dashed warning line + shaded unsafe zone, min marker, endpoint dot; hover tooltip `.tip` |
| Bar chart | `barChart()` | grouped revenue (teal) / costs (light teal) per basin, bars grow on load (`@keyframes grow`) |
| Sparkline | `spark()` | 200×36 |
| Alert row | `.alert` + `.stripe` + `.check` + `.a-status` | **tick circle** opens resolve dialog; turns green with pop animation; strikethrough title; "✓ Resolved by NAME at HH:MM · “note”" |
| Report row | `.report` + `.report-open` + `.read-btn` | unread dot; "Mark as read" button turns into green "✓ Read" |
| Tabs | `.tabs` with `role="tab"` buttons | Open/Done, All/Unread, metric tabs |
| Switch | `.switch[aria-checked]` | permissions |
| Modal | `.modal-bg > .modal` | resolve note, report, reopen confirm |
| Side sheet | `.sheet-bg > .sheet` | add member, edit permissions |
| Toast | `.toasts > .toast` | bottom centre, 4.2 s |
| Notifications | `.bell` + `.drop` | latest 5 open alerts |
| Simulator toggle | `.sim-btn` | live clock + pause/resume |
| Assistant panel | `.panel-ai`, `.ai-body`, `.msg-user`, `.msg-ai`, `.stepchip`, `.src`, `.data-used`, `.approve`, `.risk-cards`, `.cmp`, `.fb`, `.chips` | see section 6 |
| Sidebar | `.side` (white floating panel), `.farm` (green card with basin dots `.farm-dots`), `.nav-label`, nav buttons, `.user-card` | active item: deep teal pill with shadow |
| Field | `.field` + `input/select/textarea` + `.err` | validation on blur **only after typing**, and on submit; error clears as soon as fixed |

## 4. Pages

### 4.1 Website (`/`) — screenshots 01, 02, 50
Sections in order: **hero** (pill nav, mist blobs, headline "Know your water / before your **fish do.**", sub-text, buttons *Create your farm* + *Try the live demo*, underwater canvas in the lower 60% with mask fade, glass squares, 3 live reading chips) → **stats** (pinned on desktop; water level rises with scroll; 4 notched cards count up: 94% / 4.2 min / 12% / 99.6%; "Built with" row) → **loop** (3-panel hover accordion with giant 1/2/3) → **assistant** (copy + example chat card) → **CTA** (night lake canvas with fish pens and blinking sensor buoys, frosted card "Sleep through the 4 a.m. oxygen dip.") → **footer** (aqua; 3 dots bounce and become the fish logo, ring draws).
Intro: page starts at scale .9 with rounded corners over a blurred backdrop and grows to full screen, then headline words reveal from blur. Smooth scroll with Lenis. All timings are in the `LANDING PAGE MOTION` section of the reference: copy them.

### 4.2 Sign-in (`/owner-auth`, `/worker-auth`) — screenshots 03–06, 51
Split screen: left dark underwater canvas with a big quote and a live oxygen chip; right white form card.
- **Owner page:** segmented control *Sign in* / *Create farm*. Create farm fields: your name, email, password (≥ 8), farm name, company name, country.
- **Team page:** workers and technicians only; their accounts are created by the owner.
- Show/Hide password button; demo-account box; wrong credentials message; owner account on the team page (and the reverse) gets a message with a link to the right page.
- Visiting a protected page while signed out redirects to the right sign-in page with a toast.

### 4.3 App shell (all roles)
White floating sidebar (brand, green farm card with role chip + 4 basin status dots, "MENU", nav with icons and counts, user card with sign-out). Topbar: breadcrumb + page title, simulator toggle with live clock, bell with count and dropdown, *Ask the farm* button. Content area scrolls; view changes animate in (stagger fade-up). On ≤ 820px the sidebar becomes a horizontal top bar.

### 4.4 Owner
- **Overview** (10, 52): home hero (date eyebrow, "Good morning, Nadia. / Two basins need you **today.**", one-line summary, *See open alerts* + *Ask about today*, water band at the bottom) → 4 ticket cards overlapping the water (Basins, Open alerts [pink], Profit this quarter, Team) → two tiles: **Today's actions** (numbered 1/2/3, clickable) and **Basins** (dot, name, species, live O₂, badge; click opens basin) → **Revenue this quarter** (revenue / costs / profit + grouped bar chart).
- **Basins** (11): status counts + 2-column grid of basin cards (tank, 3 live readings, fish/volume/density, low-O₂ risk estimate badge).
- **Basin detail** (12, 13): back button, status, *Explain this basin*; 3 gauges (O₂ with % saturation, temperature, pH) + overnight low tile with tank; 24-hour chart with metric tabs and hover tooltip; low-oxygen prediction (probability, meter, top features, "estimate · model v1.3"); editable finances (fish count, feed, maintenance, operational, live net profit, Save, *What if…*); alerts of this basin.
- **Alerts** (14–17): intro line, tabs *Open · n* / *Done · n*; alert rows with tick circle; resolve dialog with required note and green *Mark as resolved*; row turns green with pop animation, then moves to Done; clicking a green check asks to reopen; empty state "All clear." with big check.
- **Reports** (18–20): tabs *All* / *Unread*, *Mark all as read*; rows with unread dot, author avatar, role badge, snippet, and *Mark as read* ↔ *✓ Read*; opening a report shows full text with *Close* and green *✓ Mark as read* (opening alone does **not** mark it read).
- **Team** (21–23): table (avatar, name, email, role badge, shift, permission chips, *Edit permissions*); *+ Add member* side sheet (name, email, temporary password ≥ 8, role, shift start/end) creates a real account; permissions side sheet with 5 switches (Reports, Alerts, Basins, Sensors, Maintenance), saved instantly.
- **Notifications** (24) and **assistant** (25, 26).

### 4.5 Worker
- **Today** (30): home hero "… h … min left on **your shift.**" with shift progress bar; tickets (Water alerts, My open tasks, Healthy basins, Overnight O₂ low); My tasks checklist + Needs attention; basin cards (if Basins permission).
- **Alerts** (31): water alerts only, same tick-off flow.
- **Shift report** (32): title, basin, observations; validation; "Your recent reports".
- **Basin detail** (33): like owner but finances replaced by the basin's probes and *Report a problem*.
- Menu items appear only for granted permissions (Today is always there).

### 4.6 Technician
- **Today** (40): "Two probes need **your hands.**"; tickets (Probes OK, Hardware alerts, Open tasks, Last calibration); hardware alerts + maintenance tasks.
- **Hardware alerts** (41): sensor alerts only; tick = *Mark repaired*.
- **Sensor health** (42): table with 6-hour sparkline, status (OK / Stuck / Drift), evidence, last calibration.
- **Maintenance** (43): log form (probe, work done, due date, description) + task list with status select (pending / in progress / fixed).

## 5. Behaviour rules
- Status of a basin: critical if O₂ < species critical; warning if O₂ < warning, pH or temperature outside the species range, or an open non-low alert; otherwise healthy.
- Species thresholds (seed data): tilapia O₂ warn 5 / crit 3 mg/L, temp 22–34 °C, pH 6.5–8.5; rainbow trout O₂ warn 7 / crit 5, temp 4–20, pH 6.5–8.5; common carp O₂ warn 5 / crit 3, temp 15–32, pH 6.5–9.
- O₂ % saturation = O₂ ÷ solubility(temp), solubility interpolated from FAO freshwater values 10 °C 11.28, 20 °C 9.08, 30 °C 7.54 mg/L.
- Live values update without re-rendering the whole page (values, badges, tanks, gauges, charts, counts, farm dots).
- Toasts confirm every action ("✓ Resolved", "Marked as read", "Saved", "Account created", "Task created", …).
- Escape closes modal, sheet, dropdown and assistant.
- Respect `prefers-reduced-motion` everywhere (rules exist in the reference).
- Keyboard: every clickable card/row is focusable and opens with Enter/Space; visible focus ring.

## 6. Assistant panel (screens 25, 26, 54)
Right drawer (430px; full width on phone). Header *Farm assistant* + *New chat* + close. Demo-mode banner **only when the back end runs without an API key**. Empty state: capability statement + starter chips that depend on role and page. A turn shows: user bubble → tool-step chips (spinner → ✓) → streamed text (markdown: paragraphs, lists, bold) → optional inline chart / risk cards / comparison bars → source chips → "Data used · n tool calls" (expands) → optional approval card (*Approve and create task* / *Not now*) → thumbs up/down → follow-up chips. "Explain" buttons across the app open the panel and ask a prepared question. The real behaviour (tools, streaming, RAG, guardrails) is specified in `docs/CHATBOT_UPGRADE.md`.

## 7. Screenshot index
01 website full · 02 website hero · 03 owner sign-in · 04 wrong password · 05 create-farm validation · 06 team sign-in · 10 owner overview · 11 basins · 12 basin detail oxygen · 13 basin detail temperature · 14 alerts open · 15 resolve dialog · 16 just resolved · 17 done tab · 18 reports · 19 report open · 20 all read · 21 team · 22 permissions sheet · 23 add member · 24 notifications · 25 assistant empty · 26 assistant answer · 30 worker today · 31 worker alerts · 32 shift report validation · 33 worker basin detail · 40 technician today · 41 hardware alerts · 42 sensor health · 43 maintenance · 50–54 phone (website, sign-in, overview, alerts, assistant)
