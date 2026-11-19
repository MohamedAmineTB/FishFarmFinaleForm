# FishFarm — Project Brief

> Note: `BUILD_PROMPT.md` and `docs/DESIGN_SPEC.md` take priority over this brief where they differ (for example: owners can resolve alerts; no Tailwind or Recharts).

**Tagline:** Smart Water · Smarter Farming
**What it is:** a responsive aquaculture (fish farm) monitoring and farm-management web app.
It monitors water quality (temperature, pH, dissolved oxygen) per basin, raises alerts,
manages the team (owner / worker / technician) and tracks basin finances.

---

## 0. About me and why this project exists

- I am a **beginner** developer.
- This is a **portfolio project for a work-study (alternance) application** at an IT services
  company. My target fields, in priority order:
  1. **Data Engineering**
  2. **AI / Machine Learning**
  3. **Software development**
- So the project must clearly **show skills in those three fields**, not just a nice website.
- A first version was built with Lovable (React + Supabase). I want to **rebuild it myself**
  with a stack that shows Python, SQL, data pipelines and ML.
- I will have to **explain every part in an interview**, so explanations matter as much as code.

## 1. How I want you to work with me

1. **Build the whole project, end to end, without waiting for my OK between phases.**
   Use a task list and go through all phases in section 9 in order.
2. **Test each phase before moving on** (run it, run the tests, fix errors). Never move on
   with something broken.
3. **Commit with Git after each working step**, with clear commit messages.
4. If something is unclear, make the most reasonable choice, write it down in
   `docs/DECISIONS.md`, and keep going. Only stop to ask me if you are truly blocked
   (for example a missing login or an action you cannot undo).
5. **At the end, push everything to my GitHub** in a new **public** repo named
   **`FishFarmFinaleForm`** (use `gh repo create FishFarmFinaleForm --public --source=. --push`).
   Before pushing, check that no secrets are committed (`.env` must be in `.gitignore`;
   only `.env.example` is committed).
6. Because I must explain this project in interviews, also write **`docs/HOW_IT_WORKS.md`**:
   a simple, beginner-friendly explanation of each part (pipeline, database, SQL trigger,
   API, auth, realtime, ML model, front end), with likely interview questions and answers.
   When everything is finished, give me a short summary: what was built, how to run it,
   and the GitHub link.
7. Keep the code clean, typed, commented where useful, and consistent.
8. **Authorship: this is my project, published under my name only.**
   - Do **not** mention Claude, Claude Code, Anthropic, AI assistants, or Lovable anywhere
     in the repo: README, docs, code comments, commit messages, PR descriptions.
   - Do **not** add `Co-Authored-By` or "Generated with" lines to commits or PRs.
     At the start, set this up in the project's `.claude/settings.json` (the attribution
     settings for commits and PRs set to empty) so it never happens.
   - Git commits must use my own name and email (`git config user.name` / `user.email`).

---

## 2. Tech stack (replaces the Lovable/Supabase stack)

| Layer | Technology | Shows |
|---|---|---|
| Front end | React 18 + TypeScript + Vite, the prototype's own CSS and hand-drawn SVG charts (see BUILD_PROMPT.md and DESIGN_SPEC.md) | Software dev |
| Back end API | **Python + FastAPI** (Pydantic models, OpenAPI docs) | Software dev |
| Database | **PostgreSQL** + SQLAlchemy 2.0 + Alembic migrations | SQL / Data Eng |
| Auth | JWT (access tokens), hashed passwords (bcrypt/passlib), role-based access | Software dev |
| Realtime | FastAPI **WebSockets** (live readings and alerts) | Software dev |
| Data pipeline | **Python sensor simulator + ETL** with **Pandas** (extract → validate/clean → load) | Data Eng |
| Analytics | SQL views / aggregation tables (hourly stats per basin) | Data Eng |
| Machine learning | **Scikit-learn** model predicting oxygen drops (early warning) | AI / ML |
| AI assistant | LLM API called from FastAPI (key in `.env`, with a rule-based fallback if no key) | AI |
| Packaging | **Docker + docker-compose** (db, api, pipeline, frontend) | DevOps |
| Quality | **pytest** tests, Ruff linting, **GitHub Actions** CI | Software dev |

What changes compared to Lovable:
- Supabase **Edge Functions (Deno)** → **FastAPI endpoints in Python**.
- Supabase **Row-Level Security** → multi-tenancy enforced in the **API layer**
  (every query filtered by the owner of the current user). Optional bonus: also add Postgres RLS.
- Supabase **Realtime** → **FastAPI WebSockets**.
- Client-side sensor simulator → **back-end Python simulator service** (a real data pipeline).
- Lovable AI Gateway → our own **Python AI service**.

---

## 3. Design & branding

- Professional aquatic SaaS theme: dark navy header/sidebar, clean slate-50/white cards,
  teal status highlights (exact palette in DESIGN_SPEC.md).
- AppShell: FishFarm logo (water drop with a fish and signal waves), role badge
  (Owner / Worker / Technician), farm name in the header, role-based sidebar links.
- Responsive (desktop + mobile).

---

## 4. Roles, authentication & multi-tenancy

- Roles: `owner`, `worker`, `technician`.
- Routes (front end):
  - `/` → landing page with login links
  - `/owner-auth` → owner registration (creates farm: farm name, company name, country) + login
  - `/worker-auth` → worker & technician login only (accounts are created by the owner)
  - `/owner/*`, `/worker/*`, `/technician/*` → protected by role
- Multi-tenancy:
  - Every worker and technician stores `owner_user_id`.
  - Workers and technicians can only access data of **their** farm owner.
  - Helper logic equivalent to `has_role(role, user_id)` and `get_owner_for_user(user_id)`.
- Dynamic permissions stored in `user_roles.permissions` (JSONB):
  `{ "view_reports", "view_alerts", "manage_basins", "view_sensors", "view_maintenance" }` (booleans).
  When the owner changes them, the user's navigation updates live (via WebSocket).

---

## 5. Database (PostgreSQL)

**Enums**
- `app_role`: owner, worker, technician
- `basin_status`: healthy, warning, critical, inactive
- `sensor_type`: temperature, ph, oxygen
- `sensor_status`: active, inactive, maintenance
- `alert_severity`: low, medium, high, critical
- `maintenance_status`: pending, in_progress, fixed
- `task_status`: pending, in_progress, completed

**Tables** (UUID primary keys, timestamps)
1. `users` (auth: email, password_hash) — replaces Supabase auth
2. `owners`: user_id (unique), farm_name, company_name, country, created_at
3. `profiles`: user_id (unique), name, email, updated_at
4. `user_roles`: user_id, owner_user_id, role, permissions (JSONB), created_at
5. `workers`: user_id, owner_user_id, shift_start, shift_end, created_at
6. `technicians`: user_id, owner_user_id, shift_start, shift_end, created_at
7. `basins`: owner_user_id, name, capacity, status, fish_count, feeding_cost,
   maintenance_cost, operational_cost, profit, updated_at
8. `sensors`: owner_user_id, basin_id (FK), type, status, min_value, max_value, last_value, updated_at
9. `readings`: owner_user_id, sensor_id (FK), value, recorded_at — **index on (sensor_id, recorded_at)**
10. `alerts`: owner_user_id, sensor_id (FK), type, description, severity, is_resolved (default false),
    resolved_by, resolution_notes, resolved_at, created_at
11. `maintenance`: owner_user_id, technician_user_id, sensor_id (FK), description, status, due_date, created_at
12. `reports`: owner_user_id, worker_user_id, technician_user_id, title, body, content (JSONB), generated_at
13. `tasks`: owner_user_id, worker_user_id, description, status, due_date

**Alert logic (keep it in SQL to show SQL skills)**
- A PostgreSQL **trigger** on insert into `readings`: compare `value` with the sensor's
  `min_value` / `max_value`. If out of range → insert an unresolved `alerts` row (severity based
  on how far out of range), update `sensors.last_value`, and recalculate `basins.status`.
- Managed through Alembic migrations.

**Seed data:** a script that creates a demo farm (owner, 1 worker, 1 technician, 4 basins,
3 sensors per basin, some history) so the app is never empty in a demo.

---

## 6. Data Engineering part (important for my application)

1. **Sensor simulator service** (Python, runs in its own container):
   - Every 6 seconds, generates realistic random-walk readings per sensor:
     temperature 22–26 °C, pH 6.8–7.8, dissolved oxygen 6.0–9.0 mg/L.
   - 8% chance of an out-of-range spike (to trigger alerts).
   - Also occasionally produces "dirty" data (missing values, impossible values, duplicates)
     to show the cleaning step.
2. **Ingestion / ETL pipeline:**
   - Extract raw readings → **validate and clean with Pandas** (drop impossible values,
     deduplicate, handle missing values) → load into `readings`.
   - Log how many rows were accepted / rejected.
3. **Batch aggregation job:** computes hourly stats per basin and sensor (min, max, mean)
   into an aggregation table or SQL view, used for charts and ML features.
4. **Historical backfill script:** generates e.g. 30 days of history so charts and the ML
   model have data.
5. Document the data flow with a **diagram in the README** (sensor → pipeline → DB → API → UI).

## 7. Machine Learning part

- **Goal:** predict an **oxygen drop** (below the safe threshold) in the next 30–60 minutes,
  to warn the farmer **before** it happens.
- Features: recent oxygen trend, temperature (warm water holds less oxygen), pH, time of day,
  rolling means/slopes from the aggregation data.
- Model: start simple with Scikit-learn (logistic regression or random forest),
  train on the simulated history, evaluate with clear metrics (precision, recall, confusion matrix).
- A training script (`ml/train.py`) that saves the model, and an API endpoint
  `/basins/{id}/prediction` that returns a risk score.
- In the UI: an "Oxygen risk" badge / card on the basin page.
- Keep a short `ml/README.md` explaining the approach and results in simple terms.

---

## 8. Features by role

### Owner (`/owner`)
1. **Overview:** 4 summary cards (Total Basins, Active Sensors, Active Alerts, Team Members) +
   revenue section below: Total Revenue, Total Costs, Net Profit (sum of all basins) +
   SVG bar chart: Revenue vs Total Costs per basin.
2. **Basins** (`/owner/basins`): grid with status tag, fish count, capacity.
   `/owner/basins/:id`: live cards (Temp, pH, Oxygen), real-time line chart, **ML oxygen risk**,
   editable financial cards (fish count, feeding / maintenance / operational cost, net profit) with Save.
3. **Alerts** (`/owner/alerts`): read-only, max 5 most recent unresolved alerts
   (basin name, parameter, severity badge, timestamp). Owner cannot resolve.
4. **Reports inbox** (`/owner/reports`): worker shift reports + technician maintenance logs,
   chronological, author name, role tag, timestamp, snippet; click → modal with full text.
5. **Team** (`/owner/team`): table of workers and technicians; "Add Member" (email, password,
   role, shift times); "Edit Permissions" sheet with immediate update.
6. **AI Farm Assistant:** floating chat widget (bottom right) with New Conversation button.
   The API sends a live farm snapshot (basins, fish counts, costs, profits, active alerts,
   sensors, team size, ML risk) to the LLM. Handles:
   - "How to raise revenue?" → 3–5 specific financial tips
   - "What is my risk?" → Low / Medium / High + 2–3 sentence reason
   - "Give me advice" → 3–5 operational action items
   If no API key is configured, use a simple rule-based fallback so the demo still works.

### Worker (`/worker`)
1. **Dashboard:** basin grid with status badges; click → live cards and charts.
2. **Alerts queue** (`/worker/alerts`): active alerts, **always show the basin name**;
   "Resolve" → dialog with resolution notes → mark resolved.
3. **Shift report** (`/worker/report`): title + observations + Submit → saved to `reports`,
   appears in the owner's inbox.

### Technician (`/technician`)
1. **Hardware alert queue:** sensor/equipment alerts with basin name and parameter;
   mark resolved after repair.
2. **Maintenance logging** (`/technician/maintenance`): calibration / repair / replacement,
   description, due date → `maintenance` table → visible in owner reports.

---

## 9. Build phases (do them all, in order, testing each one)

1. **Setup:** repo structure, docker-compose with PostgreSQL, FastAPI "hello world",
   React app shell, Git init, `.env.example`, `.gitignore`.
2. **Database:** SQLAlchemy models, Alembic migrations, enums, the alert trigger, seed script.
3. **Auth & roles:** register/login, JWT, role-protected routes, multi-tenancy, permissions.
4. **Data pipeline:** simulator, Pandas cleaning/ETL, aggregation job, backfill.
5. **API + realtime:** CRUD endpoints for each section, WebSockets for readings/alerts.
6. **Front end:** owner, worker and technician pages, charts, live updates.
7. **Machine learning:** training script, evaluation, prediction endpoint, UI badge.
8. **AI assistant:** chat endpoint + widget, with fallback.
9. **Quality:** pytest tests (API, pipeline, ML), linting, GitHub Actions CI.
10. **Portfolio polish:** professional README (description, screenshots/GIF, architecture
    diagram, tech stack, how to run with one `docker compose up`, what I learned),
    demo accounts, `docs/HOW_IT_WORKS.md`, then push to the new public GitHub repo
    **`FishFarmFinaleForm`**.

---

## 10. Definition of done

- `docker compose up` starts everything; demo data is loaded; I can log in as owner, worker
  and technician with demo accounts.
- Live readings update charts; out-of-range values create alerts; the ML risk shows on basins.
- Tests pass in GitHub Actions.
- The README lets a recruiter understand the project in 1 minute.
- I can explain each part (pipeline, database, trigger, API, auth, ML, front end).
