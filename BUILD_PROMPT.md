# FishFarm: full build instructions

You are building **FishFarm**, a fish-farm monitoring web app, as a real, working product:
a React front end that looks **exactly** like the approved prototype, on top of a Python
back end, a PostgreSQL database, a data pipeline, a machine-learning model and an AI assistant.

The person you work for is a beginner who can only copy and paste. **Do all the technical
work yourself.** Never ask them to type commands, edit files or choose between technical
options. When you need their approval (permission prompts), explain in one simple sentence
what you are about to do. Report progress in plain, short English.

---

## 0. Files you have (read them all before starting)

| File | What it is | Priority if files disagree |
|---|---|---|
| `BUILD_PROMPT.md` (this file) | What to build, in what order, how to check it | 1 (wins) |
| `docs/DESIGN_SPEC.md` | The design explained: tokens, components, every page, behaviour | 2 |
| `docs/design-reference.html` | The approved clickable prototype: **exact source** for CSS, SVG, icons, canvas animations, text | 2 |
| `docs/screenshots/*.png` | 36 screenshots of every page and state (desktop + phone) | 2 |
| `docs/CHATBOT_UPGRADE.md` | Full spec of the AI farm assistant | 3 |
| `docs/PROJECT_BRIEF.md` | Original product brief (roles, database, pipeline, ML) | 4 |

Open `docs/design-reference.html` in a browser (with Playwright) and click through it
before you write any front-end code. Sign in with the demo accounts:
owner `nadia@lacvert.farm`, worker `karim@lacvert.farm`, technician `samir@lacvert.farm`,
password `demo1234`.

---

## 1. Ground rules

1. **The design is approved. Do not redesign.** Port the prototype's CSS (class names
   unchanged), SVG paths, icons, canvas code and copy into React. See `DESIGN_SPEC.md` §0.
2. **No Tailwind, no UI component library, no Recharts.** Use the prototype's CSS and port
   its hand-drawn SVG charts (`lineChart`, `barChart`, `spark`, `gauge`, `tank`) to React components.
3. **Everything real.** The prototype fakes data in the browser. In the app, every number,
   alert, report, task, account and assistant answer comes from the back end and survives a refresh.
4. **Existing work:** this folder may already contain a version of the project. First run
   `git status`; commit anything uncommitted, then create a branch `redesign`. Reuse back-end
   code that already meets the spec; replace what doesn't. The front end is rebuilt to match the design.
5. **Authorship:** this is the user's project, published under their name only.
   Never mention Claude, Claude Code, Anthropic, AI coding assistants or Lovable as authors
   in the repo (README, docs, comments, commit messages, PRs). Set the project's
   `.claude/settings.json` so commits and PRs get **no** `Co-Authored-By` or
   "Generated with" lines. Commits use the user's own git name and email.
   (Naming the runtime LLM the app calls, e.g. "Claude Haiku via the Anthropic API", in the
   README's tech stack is fine: that's a dependency, not authorship.)
6. **Work autonomously** through all phases in section 5. Use a task list. **Test each
   phase before moving on.** Commit after each working step. If something is unclear,
   choose the most reasonable option, write it in `docs/DECISIONS.md`, and continue.
   Stop only if truly blocked (for example a missing login).
7. **Tools on this computer:** check that Git, Node.js 20+, Python 3.11+, Docker Desktop
   and the GitHub CLI are installed. If one is missing, install it yourself (winget on
   Windows, brew on macOS) after explaining why in one sentence.
8. **Quality over quantity.** Never leave a half-working button. If a feature can't be
   finished well, leave it out and note it in `docs/DECISIONS.md`.

---

## 2. Technology stack (fixed)

| Layer | Technology |
|---|---|
| Front end | React 18 + TypeScript + Vite; React Router (paths `/`, `/owner-auth`, `/worker-auth`, `/owner/*`, `/worker/*`, `/technician/*`); the prototype's CSS in `frontend/src/styles/`; GSAP 3.12.5 + ScrollTrigger and Lenis 1.1.13 from npm (pinned); fonts Bricolage Grotesque, Geist, Geist Mono (Google Fonts) |
| Back end | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 with pgvector; SQL trigger for alert creation; row-level security for the assistant's read-only role |
| Auth | Email + password, bcrypt hashing, JWT access token + refresh token in an httpOnly cookie; roles owner / worker / technician; multi-tenancy by `owner_user_id`; permissions JSONB checked **on the server** |
| Realtime | FastAPI WebSocket `/ws` pushing readings, alerts, task and report events per farm |
| Data engineering | Sensor simulator service + ETL with pandas (validate, clean, load) + hourly aggregation job + 30-day backfill |
| Machine learning | scikit-learn model predicting an oxygen drop before dawn; training script, metrics, `/basins/{id}/prediction` |
| AI assistant | As specified in `docs/CHATBOT_UPGRADE.md`: own `LLMProvider` (Anthropic `claude-haiku-5-5` default, OpenAI-compatible/Ollama, deterministic mock), typed read-only tools, SSE streaming, pgvector hybrid RAG, guardrails, evals |
| Quality | pytest, Ruff, ESLint + Prettier, Playwright (front-end tests + visual check), GitHub Actions |
| Packaging | Docker + `docker compose up` (db, api, simulator, frontend), `.env.example` |

---

## 3. What the prototype only faked, and how the real app must do it

| # | In the prototype | In the real app |
|---|---|---|
| 1 | Data lives in the browser and resets on refresh | Everything is stored in PostgreSQL and survives refresh and restart |
| 2 | Sign-in checks a list in the page | Real accounts, hashed passwords, JWT; session survives refresh; sign-out revokes the refresh token |
| 3 | A new farm opens with demo data | A new owner gets an **empty farm** with an empty state "Add your first basin" (button opens a side sheet: name, species, capacity m³, fish count; creates 3 probes automatically). A secondary button **"Load demo farm"** seeds the 4-basin demo so recruiters can explore |
| 4 | "Add member" creates an in-page account | Creates a real user with the temporary password; that person can sign in on `/worker-auth` |
| 5 | Permissions only hide menu items | Permissions are also enforced by the API (403 if not allowed) and pushed live over the WebSocket so menus update instantly |
| 6 | Readings come from `tick()` in the page | Readings come from the simulator → pipeline → database → WebSocket. The topbar simulator toggle calls `POST /simulator/pause|resume` (owner only; others see the state, can't change it) |
| 7 | Alerts are created in the page | Alerts are created by the SQL trigger on `readings` (and by the sensor-health job for stuck/drifting probes). Resolving stores `resolved_by`, `resolved_at`, `resolution_note`; reopening clears them; every change is broadcast |
| 8 | "Read" state of reports is in the page | Stored per user in a `report_reads` table; "Mark all as read" is one API call |
| 9 | Tasks and maintenance logs are in the page | `tasks` table (title, assignee, due, status pending/in progress/fixed, source = manual/assistant/maintenance); maintenance logs also create an owner report |
| 10 | Assistant uses prepared templates | Real assistant per `CHATBOT_UPGRADE.md`; the template answers become the **mock provider** used when no API key is set (demo banner shown only then) |
| 11 | Approve card adds a task in the page | Calls the approval-gated write tool; the task appears for the assignee live |
| 12 | Thumbs up/down shows a toast | Stored in `feedback`; shown on the AI Ops page |
| 13 | Bell lists alerts from the page | Bell shows the latest 5 open alerts the user may see, live |
| 14 | Overview figures are fixed | Computed by the API: counts, revenue/costs/profit per basin, overnight O₂ low, today's 3 actions (from the briefing service), team counts |
| 15 | Times use the browser clock | Server stores UTC; UI shows the farm's local time |

---

## 4. Database additions (on top of `PROJECT_BRIEF.md` §5)

- `basins.species` (tilapia, rainbow_trout, common_carp, sea_bass, sea_bream) and a
  `species_thresholds` table (values in `DESIGN_SPEC.md` §5 and `CHATBOT_UPGRADE.md` §5, each with `source_url` and `verified`).
- `sensors.last_calibrated_at`, `sensors.health` (ok / stuck / drift / spiky / offline), `sensors.health_note`.
- `alerts.kind` (water / sensor), `alerts.resolved_by`, `alerts.resolved_at`, `alerts.resolution_note`.
- `report_reads (report_id, user_id, read_at)`.
- `tasks.source`, `tasks.status` (pending / in progress / fixed), `tasks.assignee_user_id`.
- `owners.timezone` (default Europe/Paris).
- Assistant tables from `CHATBOT_UPGRADE.md` (conversations, messages, kb_documents, kb_chunks, llm_requests, llm_usage, feedback, briefings).
- Seed script: demo farm "Lac Vert" exactly as in the prototype (4 basins: Basin 1 Nile tilapia 4,200 fish 180 m³; Basin 2 Nile tilapia 3,800 / 160; Basin 3 rainbow trout 2,600 / 140; Basin 4 common carp 3,100 / 200; finances as in the prototype; team Karim, Léa, Inès (workers), Samir (technician) with the same shifts and permissions; the 4 reports; the 2 tasks; 30 days of readings with the same day-night pattern, Basin 3 night oxygen dip, Basin 2 afternoon pH peak, Basin 4 temperature probe stuck).

**Change from the original brief:** owners **can** resolve alerts (tick circle), like workers and technicians.

---

## 5. Build phases (do them all, in order, testing each one)

**Phase 0: Prepare.** Locate and read every file in section 0. Inspect the existing code and
write `docs/GAP_ANALYSIS.md` (what exists, what changes). Set up `.claude/settings.json`
(no attribution), git identity check, branch `redesign`.

**Phase 1: Back-end core.** Models + Alembic migrations, alert trigger, auth (register owner,
sign in owner/team, refresh, sign out), tenancy helpers, permissions dependency, all CRUD
endpoints the pages need (basins, sensors, readings, alerts resolve/reopen, reports + read
state, tasks, team + permissions, finances, overview summary), seed + demo loader.
Tests: pytest for auth, tenancy (owner A can't see owner B), permissions (403), alert trigger.

**Phase 2: Data pipeline + realtime.** Simulator service (6 s readings, random walk per species,
8% spikes, occasional dirty data), pandas ETL with accept/reject logging, hourly aggregation,
sensor-health job (stuck / drift / spiky / offline from rolling statistics), backfill,
WebSocket broadcasting, simulator pause/resume.

**Phase 3: Front-end foundations.** Vite + React + TS; port tokens, fonts and the full
stylesheet from `design-reference.html` into `frontend/src/styles/` (keep class names);
API client with auth and refresh; WebSocket store; routing and protected routes; app shell
(white floating sidebar, topbar with simulator toggle, bell, assistant button); modal, side
sheet and toast components; field validation (blur after typing, on submit).

**Phase 4: Website + sign-in pages.** Port the website exactly (all sections, canvas scenes,
GSAP/Lenis motion, intro, pinned stats, accordion, night lake, footer logo animation).
Port both sign-in pages with all states (screens 03–06, 51). The website "Try the live demo"
button signs in to the demo owner account.

**Phase 5: Owner pages.** Overview, Basins, Basin detail (gauges, chart with tooltip,
prediction, editable finances), Alerts (tick-off flow, Open/Done tabs, reopen), Reports
(read/unread, mark all), Team (add member sheet, permissions sheet), notifications.
Match screens 10–24.

**Phase 6: Worker and technician pages.** Worker Today, Alerts, Shift report, Basin detail;
Technician Today, Hardware alerts, Sensor health, Maintenance. Menus follow permissions.
Match screens 30–43.

**Phase 7: Machine learning.** Features (evening O₂ decline rate, temperature, hour of day,
feeding load, rolling stats), train/evaluate (precision, recall, confusion matrix), save model,
prediction endpoint, shown on basin cards, basin detail and Today pages. `ml/README.md`.

**Phase 8: AI assistant.** Build everything in `docs/CHATBOT_UPGRADE.md` (its phases 1–7),
using the prototype's panel design (screens 25, 26, 54). All "Explain" and "Ask" buttons in the
app open the panel with the prepared question.

**Phase 9: Tests and CI.** pytest (API, pipeline, ML, assistant tools, tenancy), Playwright
end-to-end for the main flows of each role (sign in, resolve an alert, mark a report read,
add a member, change a permission, send a shift report, log maintenance, ask the assistant
in mock mode), evals, Ruff/ESLint; GitHub Actions running all of it.

**Phase 10: Visual check (mandatory).** With Playwright, capture the same 36 states as
`docs/screenshots/` (same names, same viewport sizes: 1440 wide for desktop, 390×844 for
phone) into `docs/screenshots-build/`. Compare each pair side by side and fix every
difference in layout, colour, spacing, sizes or content (fonts are the only expected
difference, since the reference screenshots used a fallback font). Write
`docs/VISUAL_CHECK.md` listing each screen as ✅ with any remaining note. Do not finish
until every screen matches.

**Phase 11: Finish.** README written for recruiters (what it does, screenshots, architecture
diagram, tech stack, data flow, ML results, assistant eval scores, security design, limitations,
how to run with one `docker compose up`, demo accounts). Update `docs/HOW_IT_WORKS.md`
(simple explanations of each part + interview questions and answers). Check that
`docker compose up` works with **no API key** (mock assistant). Make sure no secret is
committed. Merge `redesign` into `main` and push to the user's GitHub repo
**`FishFarmFinaleForm`** (create it as public with `gh repo create` if it doesn't exist).

---

## 6. Definition of done

- Every page and state in `docs/screenshots/` exists in the app and matches it (Phase 10 passed).
- Every button, link, tab, switch, checkbox and form does something real, and its result survives a refresh.
- The three demo accounts work; a new owner can create a farm, add a basin, add a worker, and that worker can sign in.
- Readings update live; alerts appear by themselves and can be ticked off and reopened; reports can be marked read/unread.
- The assistant streams real answers with tools, charts, sources and approval cards when an API key is set, and works in demo mode without one.
- All tests and checks pass in GitHub Actions.
- The code is on GitHub in `FishFarmFinaleForm`, with no mention of AI coding tools as authors.

When everything is done, tell the user in simple words: what was built, how to open it
(start it for them and give the local address), how to add an Anthropic API key later if
they want real AI answers, and the GitHub link.
