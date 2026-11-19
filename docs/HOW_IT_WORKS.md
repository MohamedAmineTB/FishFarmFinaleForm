# How FishFarm works

A plain-language tour of every part, with the questions an interviewer is likely to ask and short answers.

---

## 1. The big picture

A fish farm has basins (ponds or tanks). In each basin, three probes measure the water: **temperature**, **pH**
(acidity) and **dissolved oxygen** (DO). Fish die quickly when oxygen gets too low, and oxygen is usually lowest just
before dawn. FishFarm watches every basin all the time, warns the right person, and explains what to do.

Four programs run together (four Docker containers):

| Container | What it does |
|---|---|
| `db` | PostgreSQL: stores everything and runs the alert engine (a trigger). |
| `pipeline` | Pretends to be the probes, cleans the data, loads it, and runs background jobs. |
| `api` | FastAPI: login, permissions, all the data the screens need, live events, the AI assistant. |
| `frontend` | The React website, served by nginx (which also forwards `/api` and `/ws` to the API). |

---

## 2. Data pipeline (data engineering)

**Simulator** (`backend/app/pipeline/simulator.py`). Every 6 seconds it creates one reading per probe. Values follow a
day-night curve: oxygen peaks mid-afternoon, when algae make oxygen, and is lowest before dawn. Each basin has a
profile (base value and daily amplitude) and some random noise. On purpose, it sometimes sends:
- a **spike**: one out-of-range reading, which should raise an alert;
- **dirty data**: a missing value, an impossible value (pH 15) or a duplicate row;
- a **probe fault**: the probe gets stuck at one value, or starts drifting.

**ETL** (`etl.py`), meaning Extract, Transform, Load. The raw batch becomes a pandas DataFrame. Rows with unknown
probes, missing values or physically impossible values are rejected, and duplicates are removed. The counts per
reason go into the `etl_runs` table, so we can prove what was cleaned. The clean rows are inserted into `readings`.

**Jobs** (`runner.py`):
- every minute, the **sensor-health job** (`health.py`), which uses rolling statistics:
  - *stuck*: the same value for an hour or more;
  - *spiky*: several jumps much bigger than usual;
  - *drift*: the last 6 hourly means all sit above or below the probe's own 7-day baseline;
  - *offline*: no reading for 10 minutes.

  Stuck and offline probes open a "hardware" alert for the technician.
- every 5 minutes, the **hourly aggregation** (min / max / mean per probe and hour into `hourly_stats`) and the
  **oxygen predictions**.

**Backfill** (`backfill.py`) generates 30 days of history at 5-minute steps (about 104,000 rows) and loads them with
PostgreSQL `COPY`, the fastest way to bulk-insert. It switches the alert trigger off during the load, so history doesn't
create thousands of alerts.

**Interview questions**
- *Why pandas?* It makes the validation rules short and readable (vectorised filters), and the same code could clean a
  CSV export from real probes.
- *What happens to bad data?* It is rejected, not fixed, and counted by reason in `etl_runs`. Silently "fixing" a sensor
  value could hide a real problem.
- *How do you tell a broken probe from a real water problem?* Real water always moves a little, so a flat line for an
  hour is a probe problem. Drift is checked against the probe's own normal daily pattern. Water problems change smoothly;
  probe problems are flat lines or jumps.

---

## 3. Database and the SQL alert engine

PostgreSQL holds the farms, users and roles, basins, sensors, readings, alerts, reports (with per-user read state),
tasks, maintenance logs, predictions and the assistant's tables. **Alembic migrations** create and update the schema,
so the database can be rebuilt from scratch with `alembic upgrade head`.

**The alert trigger** (`alembic/versions/0001_core.py`, function `ff_evaluate_reading`) runs inside the database for
every new reading:
1. it saves the latest value on the sensor;
2. it compares the value with the sensor's safe range (copied from the species thresholds: e.g. trout oxygen warning 7 mg/L);
3. if out of range and no alert is open for that probe, it inserts an alert with a title, a description and a severity
   (critical below the species critical oxygen level, otherwise by how far out of range);
4. it recalculates the basin status (healthy / warning / critical);
5. it calls `pg_notify`, so the API can push the new alert to the screens.

**Interview questions**
- *Why put the alert logic in SQL?* Every reading, from any program, goes through the same rule. It is atomic (the
  reading and its alert are saved together) and it can't be bypassed by a bug in one service.
- *How do you avoid alert floods?* At most one open alert per probe; repeated bad readings don't add rows until someone
  resolves the alert.
- *What is an index for?* `readings(sensor_id, recorded_at)` makes "last 24 hours of this probe" fast even with millions of rows.

---

## 4. The API (FastAPI)

Endpoints are grouped by area (`backend/app/routers/`): auth, farm (overview, today, live state, simulator, demo), basins,
alerts, reports, team, tasks/maintenance/sensors, and the assistant. Pydantic models validate every request body:
a too-short password or a wrong email gets a 422 with a clear message.

**Interview questions**
- *How does the API know which farm the data belongs to?* From the signed-in user: workers and technicians are linked to
  their owner in `user_roles.owner_user_id`. Every query filters by that owner id; it is never read from the request.
- *What happens if I ask for another farm's basin?* "404 not found". We don't even say it exists. Tests check this.

---

## 5. Authentication and permissions

- Passwords are hashed with **bcrypt**, never stored.
- At sign-in the API returns a short-lived **JWT access token** (15 minutes, kept in memory by the browser) and sets a
  **refresh token** in an **httpOnly cookie** (JavaScript can't read it, which protects it from XSS). The refresh token is stored
  hashed in the database, **rotated** every time it is used, and **revoked** on sign-out.
- Roles: owner, worker, technician. The owner switches pages on and off per member (reports, alerts, basins,
  sensors, maintenance). These **permissions are checked by the API** (403 if not allowed), not just hidden in the menu.
  When the owner changes one, a WebSocket event updates the member's menu immediately.

**Interview questions**
- *Why not keep the JWT in localStorage?* Any injected script could steal it. In memory plus an httpOnly refresh cookie is safer.
- *What if a token is stolen?* The access token expires in 15 minutes; the refresh token can be revoked and is rotated.

---

## 6. Realtime

The simulator, the API and the trigger all publish events with `pg_notify('ff_events', ...)`. The API keeps one
listening connection (`backend/app/events.py`) and forwards each event to the WebSocket clients **of the same farm**. The
React app then refreshes just what changed: live values, tank levels, gauges, badges, counters, menus.

*Why LISTEN/NOTIFY instead of Redis?* It is already in PostgreSQL, events can be sent from inside the trigger, and there is
one less service to run.

---

## 7. Machine learning

The question: "will oxygen fall below the warning level for this species before 06:00?" Each training sample is one basin at
one hour. The features describe the water so far: the evening oxygen decline, last night's low, the rolling mean and spread,
temperature, pH, time of day and feeding load. A random forest is trained on the first 75 % of the 30 days and tested on the
last 25 % (by time, never shuffled). See [`ml/README.md`](../ml/README.md) for the scores and the honest comparison with a
simple baseline.

**Interview questions**
- *Why split by time?* Neighbouring hours of the same night are nearly identical; a random split would leak them into
  the test set and give scores that are too good.
- *Why does the baseline win?* The simulated nights are very regular. On real data, weather and algae make nights differ, which
  is where a model helps. I report it instead of hiding it.
- *Precision or recall?* Recall: a missed oxygen dip can kill fish, while a false alarm costs one skipped meal.

---

## 8. Front end

React 18 with TypeScript. The design was approved as a single-file prototype, so its CSS was moved unchanged into
`frontend/src/styles/` (same class names). Its chart functions (line, bar, sparkline, gauge, tank) were rewritten as React
components that draw the same SVG. The canvas scenes and the website motion (GSAP + Lenis) were ported too.

- `api/client.ts`: fetch wrapper; on a 401 it refreshes the token once and retries.
- `api/realtime.tsx`: the WebSocket (with reconnect) and a small store of the live farm state.
- `components/ui.tsx`: modal, side sheet, toasts and form validation (errors appear on blur only after typing, and on
  submit, and clear as soon as the value is fixed).
- `scripts/capture.mjs` + `docs/VISUAL_CHECK.md`: every screen was compared with the approved screenshots.

---

## 9. The AI farm assistant

**Idea:** a narrow copilot. Deterministic code owns the alerts, thresholds, chemistry and who-can-see-what. The language
model only decides which trusted tool to call and explains the result in plain words.

**How one question is answered** (`backend/app/assistant/agent.py`):
1. The API checks limits (10 per minute, 100 per day, a daily token budget, 2,000 characters).
2. It builds the prompt: the versioned system prompt (rules: lead with the answer, never invent numbers, cite sources,
   stay in scope, answer in the user's language), plus a small **farm index** (basins, status, open alerts, the user's role and page).
3. The model streams back either text or a **tool call**, for example `get_readings(Basin 3, dissolved_oxygen)`.
4. The tool validates its arguments with Pydantic and reads the database **as the read-only `ai_reader` role**. Row-level
   security only shows rows of the user's farm, whose id the server sets from the JWT. The result goes back to the model
   inside `<tool_data>` tags, marked as data.
5. This repeats up to 5 times, then the answer streams to the browser as Server-Sent Events. Charts, risk cards, sources and
   follow-up chips are built from the tool results by our code, not by the model.
6. **Write actions** (create a task, acknowledge an alert) are never executed by the model: they become an approval card, and
   run only when the user clicks Approve.
7. The request is logged (latency, tokens, cost, tools, retrieved documents, feedback) for the AI Ops page.

**Providers:** Anthropic (Claude Haiku by default, with the system prompt cached), any OpenAI-compatible server (for example
Ollama, offline), or the **mock**. The mock is a deterministic stand-in used automatically without an API key: it picks real
tools from the question and fills templates with the tool results only, so the demo shows real data.

**Knowledge base (RAG):** 11 short notes written in my own words from FAO, UF/IFAS, SRAC and OMAFRA, with links. An ingestion
script cuts them into chunks by heading and computes embeddings. A question is searched two ways, by full text (PostgreSQL
`tsvector`) and by vector similarity (pgvector), and the two rankings are merged with **Reciprocal Rank Fusion**
(score = Σ 1 / (50 + rank)).

**Evaluation:** 44 golden cases (knowledge, live data, out of scope, actions, prompt injection, another farm's data, worker
asking about money, French and Arabic) run in CI. Metrics: tool correctness, retrieval hit@4 and MRR, refusals, approvals,
forbidden content, language, and **number grounding** (every number in the answer must appear in that turn's tool results).

**Interview questions**
- *How do you stop the assistant from showing another farm's data?* Three layers: the tools have no owner-id argument (the
  server injects it), every tool queries through a read-only role with row-level security, and tests try every tool with
  another farm's basin id.
- *How do you limit hallucinated numbers?* The rule is in the prompt, every number must come from a tool, and the
  number-grounding eval measures it (95 % in demo mode; the rest are advice times in templates).
- *What is prompt injection here?* A worker could write "ignore previous instructions…" in a report. Tool output is wrapped
  and labelled as data, answers are rendered as escaped markdown, write actions need human approval, and an eval case checks it.
- *Why not LiteLLM or LangChain?* The loop is ~200 lines and fully understood. Fewer dependencies (LiteLLM had a supply-chain
  compromise in 2026) and it makes the security design easy to explain.
- *What would you add next?* LLM-judged faithfulness with an API key in CI, real sentence-transformers embeddings in the
  image, and notifications (SMS/email) for critical alerts.

---

## 10. Tests and CI

- **pytest (44 tests):** auth, tenancy (owner A can't see owner B), permissions (403), the alert trigger, workflows,
  the pipeline (cleaning, health classifier, simulator), WebSocket isolation, ML, the assistant (RLS, every tool across
  tenants, streaming, approvals, rate limits, injection) and the golden set.
- **Playwright (13 flows):** each role's main journeys in a real browser.
- **GitHub Actions:** lint + tests + evals, front-end lint/format/build, end-to-end tests, and a `docker compose up`
  smoke test without an API key.
