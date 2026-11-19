# Gap analysis

## What exists (start of the rebuild)

| Item | State |
|---|---|
| `BUILD_PROMPT.md`, `docs/PROJECT_BRIEF.md`, `docs/DESIGN_SPEC.md`, `docs/CHATBOT_UPGRADE.md` | Specifications, complete |
| `docs/design-reference.html` | Approved clickable prototype (single file: CSS, SVG charts, canvas scenes, template assistant, all data simulated in the browser) |
| `docs/screenshots/` | 36 reference screenshots (desktop 1440 px wide, phone 390×844) |
| Back end, database, pipeline, ML, front end | **None.** The GitHub repository only contained a README. |

There is no earlier code to reuse, so every layer is built from scratch.

## What changes from the prototype

| Prototype | Real application |
|---|---|
| One HTML file, hash routing | React 18 + TypeScript + Vite, React Router (`/`, `/owner-auth`, `/worker-auth`, `/owner/*`, `/worker/*`, `/technician/*`) |
| CSS inside `<style>` | Same CSS, unchanged class names, split into `frontend/src/styles/*.css` |
| `lineChart`, `barChart`, `spark`, `gauge`, `tank` string builders | React components producing the same SVG |
| `S` object, `tick()` | PostgreSQL + FastAPI; readings come from the simulator service through the pandas ETL |
| Alerts created by `tick()` | SQL trigger on `readings` + sensor-health job |
| Accounts list in the page | `users` table, bcrypt, JWT access token, refresh token in an httpOnly cookie |
| Permissions only hide menu items | Checked by the API (403) and pushed live over the WebSocket |
| Template answers | Agent loop with typed read-only tools; the templates become the deterministic `mock` provider |
| Thumbs, approvals, read state, tasks | Stored in `feedback`, `tasks`, `report_reads` tables |

## Machine-specific notes

- No Docker on the development machine: local development uses a private PostgreSQL 18 cluster on port 5433; Docker Compose and GitHub Actions use the official `pgvector/pgvector:pg16` image. See `DECISIONS.md`.
