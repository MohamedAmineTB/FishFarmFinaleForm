# FishFarm — AI Farm Assistant Upgrade (v2)

Read this whole file before starting. It upgrades the existing **AI Farm Assistant** in this
project into a professional, grounded, secure, tested farm copilot. All rules from
`BUILD_PROMPT.md`, `docs/PROJECT_BRIEF.md` and `CLAUDE.md` still apply (authorship rules included). The panel's look is the one in `docs/design-reference.html`.

## 0. How to work

1. **First, inspect what exists**: the current chatbot code (back end + front end), the
   database models, auth, the ML prediction, docker-compose. Write a short gap analysis in
   `docs/assistant/GAP_ANALYSIS.md` (what exists, what changes). Reuse what is good.
2. Then **build everything in this file, phase by phase (section 9), without waiting for my OK**.
   Use a task list. **Test each phase** (run it, run tests, fix errors) before moving on.
3. **Commit after each working step** with clear messages. At the end, push together with the rest of the build, as described in `BUILD_PROMPT.md`.
4. If something is unclear, choose the most reasonable option, log it in `docs/DECISIONS.md`,
   and continue. Stop only if truly blocked (e.g. a missing login).
5. Authorship: no mention of Claude Code / AI coding assistants / Lovable as authors anywhere
   (README, comments, commits). No `Co-Authored-By` or "Generated with" lines.
   (Naming the LLM *the app uses at runtime*, e.g. "Claude Haiku via the Anthropic API",
   in the README tech stack is fine — that's a dependency, not authorship.)
6. Update `docs/HOW_IT_WORKS.md` with a beginner-friendly section about the assistant and
   likely interview questions + answers about it.
7. **Quality over quantity.** Finish phases 1–5 and 7 completely and polished before the
   smart features of phase 6. Never leave a half-working feature in the app: if something
   can't be finished well, leave it out and note it in `docs/DECISIONS.md`.

## 1. Core design principle

The assistant is a **narrow farm copilot, not a general chatbot**. Deterministic code owns
alerts, thresholds, chemistry and tenant boundaries. The LLM only **chooses which trusted tool
to call and explains the result**. It is never the source of critical alerts.

## 1b. Personality and answer rules (put these in the system prompt)

Write the system prompt in `backend/app/assistant/prompts/system.md` (versioned, with a
`PROMPT_VERSION` logged on every request). It must make the assistant:

- **Lead with the answer**, then the reason, then **1–3 concrete actions**. Short by default
  (≈120 words), longer only when asked or for reports.
- **Never invent numbers.** Every number (reading, cost, threshold, probability) must come
  from a tool result or a cited knowledge chunk, always **with units and time**
  ("5.8 mg/L at 04:30"). If data is missing, say so and say what would be needed.
- **Use the farmer's words**, not jargon; explain technical terms in one short phrase.
- **Answer in the user's language**: French, English or Arabic (auto-detected).
- **Be honest about uncertainty**: predictions and advice are labelled as estimates; when
  sources disagree (e.g. trout temperature limits), say so.
- **Safety first**: if any basin is in a critical state, mention it first, whatever the
  question was.
- **Stay in scope** (this farm, fish farming, its data). Politely refuse the rest and say
  what it can help with.
- **Adapt to the role** of the user:
  - Owner → business + overview (profit, risk, team, priorities).
  - Worker → "what do I do now", step-by-step checklists, their basins and alerts.
  - Technician → sensor health, troubleshooting, calibration and maintenance.

## 2. LLM provider layer

- Write a small `LLMProvider` interface yourself (≈50 lines), e.g.
  `stream_chat(messages, tools) -> AsyncIterator[Event]`, selected by env var `LLM_PROVIDER`:
  - `anthropic` (default) — model `claude-haiku-5-5`, optional switch to a bigger model via
    `LLM_MODEL`. Use the official `anthropic` Python SDK. Enable **prompt caching** on the
    system prompt + farm index.
  - `openai_compat` — any OpenAI-compatible endpoint (OpenAI, **Ollama** for offline/local).
  - `mock` — deterministic answers that **still call the real tools**, so the demo works
    with **no API key**. This must be the automatic fallback when no key is set, with a
    visible "Demo mode" banner in the UI.
- **Do not use LiteLLM** (supply-chain compromise in March 2026). Pin dependencies.
- API key only in back-end `.env` (never in the React bundle). Commit only `.env.example`.

## 3. Agent loop and tools

- Hand-written loop: stream → tool call → execute → feed result back → continue.
  Max **5 tool iterations**, max **800 output tokens**, input capped at **2,000 characters**.
- System prompt contains: role and scope, capability statement, rules (cite sources, label
  predictions as estimates, refuse out-of-scope), and a compact **farm index** (< ~500 tokens:
  basin ids, names, species, status, open-alert count).
- **Typed, read-only tools** (Pydantic-validated arguments, compact JSON results with units and
  timestamps, size limits). **No tool takes an `owner_id` argument**: the owner comes from the
  JWT on the server and is injected into the tool context.

| Tool | Arguments | Returns / limits |
|---|---|---|
| `list_basins` | – | id, name, species, status, latest reading summary |
| `get_basin_status` | `basin_id` | latest temp/pH/DO (+ DO % saturation), species thresholds, open alerts, last maintenance |
| `get_readings` | `basin_id`, `metric` ∈ {temperature, ph, dissolved_oxygen}, `start`, `end`, `aggregate` ∈ {raw, hourly, daily} | min/max/mean + series; max 30-day range, max 200 points |
| `get_alerts` | `basin_id?`, `status` ∈ {open, resolved, all}, `limit ≤ 50` | alerts |
| `get_maintenance` | `basin_id?`, `upcoming_only`, `limit ≤ 50` | maintenance items |
| `get_financials` | `basin_id?`, `period` ∈ {month, quarter, year} | revenue, costs, margin, KPIs (cost per basin, feed cost share, profit per fish) |
| `get_oxygen_prediction` | `basin_id` | ML probability of an oxygen drop, horizon, top features, model version, `is_estimate: true` |
| `search_knowledge` | `query`, `species?` | top-k knowledge chunks with doc_id, title, section, url, year |
| `get_sensor_health` | `basin_id?` | per sensor: OK / stuck (flat line) / spikes / drift / missing data / out of physical range, with evidence; classification **"sensor problem → technician"** vs **"water problem → worker"** |
| `compare_basins` | `metric`, `period` | ranking of basins (e.g. avg DO, alerts count, margin, cost per fish) |
| `simulate_scenario` | `basin_id`, changes (feed cost %, fish count, sale price/kg, FCR, mortality %) | deterministic what-if calculation: projected costs, revenue, profit vs current; `is_estimate: true` |
| `get_farm_briefing` | `date?` | pre-computed daily summary: overnight DO minimums, new/open alerts, ML risk per basin, maintenance due, yesterday's key numbers |
| `create_maintenance_task` / `acknowledge_alert` | typed fields | **write tools — executed only after the user clicks Approve in the UI** |

- A `basin_id` belonging to another owner returns a generic **"not found"**.
- Validation errors are returned as tool results so the model can recover.

## 4. Security (multi-tenancy + guardrails)

- Assistant DB access goes through a dedicated **read-only role `ai_reader`** that can only
  `SELECT` from an **`ai` schema of views** over the base tables.
- **PostgreSQL Row-Level Security** on the underlying tables:
  `owner_user_id = current_setting('app.owner_id')::uuid`. The **server** sets it per
  transaction: `SELECT set_config('app.owner_id', :id_from_jwt, true)`. Never the model.
- Views created with **`WITH (security_invoker = true)`** (PostgreSQL 15+) — otherwise RLS
  silently doesn't apply through views. Add a test proving owner A cannot see owner B's data
  through every tool.
- `statement_timeout` ≈ 15 s for the `ai_reader` session.
- **Prompt-injection defence**: user-written text (reports, maintenance notes, alert
  descriptions) is untrusted. Wrap tool output in `<tool_data>…</tool_data>` marked as data;
  render model output as **sanitized markdown (no raw HTML)**; no secrets in the system prompt.
  Add an eval case with a malicious maintenance note ("ignore previous instructions…").
- **Cost & abuse limits**: per user 10 requests/min and 100/day; daily token budget tracked in
  an `llm_usage` table; friendly error when exceeded.
- Out-of-scope questions → polite refusal + what it *can* help with.

## 5. Aquaculture domain knowledge

- Add a `species` field to basins (if missing) and a **`species_thresholds` table**:
  species, metric, optimal_min/max, warning, critical, emergency levels, unit, `source_url`,
  `verified` (bool). The alert engine and `get_basin_status` read from it.
- Seed with these sourced values (cite in `source_url`):
  - **Tilapia**: prefers 31–36 °C; tolerates DO < 1 ppm (FAO Nile tilapia fact sheet).
  - **Rainbow trout**: optimal 13–18 °C, DO 80–100 % saturation, pH 7–8 (OMAFRA 2024);
    FAO: best < 21 °C, pH 6.5–8.5, DO near saturation. Sources differ on upper tolerance
    (24 vs 27 °C) — keep the conservative one and note it.
  - **Atlantic salmon**: growth reduction < 70 % DO saturation, stress < 60 %, critical < 39 %
    (Stehfest et al. 2017, Scientific Reports); prefers ≈ 17 °C, avoids > 20 °C.
  - **Common carp**: optimal 23–30 °C, pH 6.5–9.0, tolerates DO down to 0.3–0.5 mg/L (FAO).
  - **Generic warm-water default**: DO warning < 5 mg/L (UF/IFAS FA031), critical < 3,
    emergency < 2 mg/L. Salmonids: warning < 80 %, critical < 60 %, emergency < 40 % saturation.
    (These cut-offs are design choices — mark them `verified=false`.)
  - **Sea bass / sea bream**: no verified values → rows flagged `verified=false`, do not invent.
- **Python helpers (unit-tested)**:
  - DO % saturation from temperature using the FAO freshwater solubility table
    (11.28 mg/L at 10 °C, 9.08 at 20 °C, 7.54 at 30 °C), interpolated.
  - Un-ionized (toxic) ammonia fraction from pH and temperature. **Test against the published
    values: 0.0502 at 24 °C / pH 8 and 0.3456 at 24 °C / pH 9** (UF/IFAS). Toxic above
    0.05 mg/L NH3; nitrite toxic from 0.10 mg/L. Add ammonia/nitrite as optional
    manual-entry readings.
- Knowledge the assistant should be able to explain (put in the knowledge base): the daily
  DO cycle (peak mid-afternoon, minimum just before dawn), low-DO risk higher above 27 °C,
  oxygen emergency actions (stop feeding 1–3 days, aerate until after sunrise, partial water
  exchange 25–50 % in tanks/small ponds, don't aerate supersaturated afternoon water), feed
  as the biggest cost (≈45–55 % for US catfish), FCR, survival, stocking density.
- Make the ML oxygen model use these features if it doesn't already: evening DO decline rate,
  water temperature, hour of day, feeding load.

## 6. Knowledge base (RAG) in PostgreSQL

- Enable **pgvector**. Tables `kb_documents` and `kb_chunks` (300–800-token chunks split on
  headings; doc_id, title, section, url, publisher, year, licence, `tsvector` + `embedding`).
- **Hybrid search** SQL function: full-text (GIN index) + vector similarity (HNSW index),
  merged with **Reciprocal Rank Fusion** (k = 50).
- Embeddings with a **local multilingual model** via sentence-transformers (BGE-M3 or
  Nomic Embed v2) — questions may come in French or English. No paid embedding API.
- Corpus (in `kb/` as markdown, with an ingestion script = a small data pipeline):
  write **paraphrased** notes in your own words with citations and links from FAO (post-2018
  FAO docs are CC BY-NC-SA 3.0 IGO), SRAC and UF/IFAS fact sheets — don't copy full texts.
  Include the facts from section 5. Flag old figures (year) in answers.
- Answers that use knowledge must show **citations** (title + link).

## 7. Streaming, memory and front end

**Streaming**: `POST /api/chat/stream` returning FastAPI SSE (`EventSourceResponse`, FastAPI
≥ 0.135) with events: `token`, `tool_call` (name + short label, e.g. "Checking Basin 2
readings…"), `tool_result` (summary), `chart` (series payload), `source`, `approval_request`,
`done` (message_id, token usage, cost), `error`. Stop the loop if the client disconnects.
React reads it with `fetch` + `ReadableStream` (JWT in the Authorization header). Stop button
wired to an `AbortController`.

**Memory**: tables `conversations` (title auto-generated, rolling `summary`) and `messages`
(role, JSONB content incl. tool calls, tokens, model), under owner RLS. Context per turn =
cached system prompt + farm index + summary + last 10–20 messages (old tool results trimmed).
Summarize old turns when context exceeds ~20K tokens. Conversation history list in the panel,
"New conversation" button.

**Front-end panel** (match the app's existing design system, polished and professional):
- Floating button → **side panel** on desktop, full-screen drawer on mobile.
- **Page-aware context**: sends current page, selected basin and date range.
- **Empty state**: short capability statement + **starter prompt chips per page**, e.g.
  Basin page: "Why did oxygen drop in this basin last night?", Alerts: "Summarize today's
  critical alerts", Overview/finance: "Compare margin per basin this quarter",
  plus "What is my risk today?", "How can I raise revenue?", "Give me 3 actions for this week".
- Streaming text with **tool-step status chips**; markdown rendered safely while streaming.
- **Inline SVG charts (ported from the prototype)** when a tool returns a time series or comparison.
- **"Sources"** chips (knowledge citations) and a **"Data used"** chip that expands to show
  which tools/arguments were used.
- **Follow-up suggestion chips** after each answer.
- **Thumbs up/down** with optional reason, stored in a `feedback` table.
- **Approval cards** for write actions ("Create task: clean aerator, Basin 2, tomorrow —
  Approve / Cancel"); runs only after Approve.
- "Estimate" badge on predictions; "Demo mode" banner when using the mock provider;
  clear error and rate-limit messages.
- Owner sees the full assistant. Workers/technicians: optional limited version
  (alerts + their basins only), respecting their permissions.

## 8. Evaluation & observability (very important for my portfolio)

- `evals/golden.jsonl` with **~40 cases** in 4 groups: knowledge questions, live-data
  questions, out-of-scope questions (must refuse), action requests (must ask approval).
  Include the prompt-injection case and a cross-tenant case.
- Metrics: tool-call correctness (DeepEval `ToolCorrectnessMetric`, no LLM needed),
  retrieval hit@k and MRR against expected doc_ids, then answer faithfulness/relevancy
  (DeepEval or RAGAS) — LLM-judged metrics only when an API key is present.
- Runs with **pytest**; deterministic part runs in **GitHub Actions** on every PR/push, using
  seeded data and the mock provider. Publish the score table in the README.
- Log every assistant request in an `llm_requests` table: latency, tokens, estimated cost,
  tools called, retrieved doc ids, feedback. Build an owner-only **"AI Ops" page**: requests
  per day, average latency, cost, most-used tools, thumbs-up rate (SVG charts from the prototype).
- Optional: Langfuse tracing if `LANGFUSE_*` env vars are set (free tier).
- Extra eval checks:
  - **Number grounding** (deterministic, no LLM): every number in an answer must appear in
    that turn's tool results or retrieved chunks (with rounding tolerance). Report the
    grounding rate in the README.
  - **Multilingual** cases: the same questions in French, English and Arabic.
  - **Sensor-fault detection accuracy** on seeded faults (precision / recall table).
  - **Role cases**: a worker must not get owner-only financial data.

## 8b. Smart features (what makes it stand out)

These turn the chatbot into a real farm copilot. Build them in phase 6, each one complete.

1. **Daily briefing**: a "Today on your farm" card at the top of the owner overview (and a
   shorter shift briefing for workers), generated once per day from `get_farm_briefing`,
   cached in a `briefings` table, with a Refresh button. Format: 3–5 bullet points and
   "Top 3 actions today". Works in mock mode too (template-based).
2. **"Explain this" buttons** everywhere it makes sense: on each alert, each chart, the
   oxygen-risk badge and the financial cards. One click opens the assistant panel with the
   context pre-filled and an instant explanation (why it happened, is it serious, what to do).
3. **Sensor health & fault detection (data engineering)**: a Pandas job computes sensor
   health from rolling statistics (flat line, sudden jumps, drift vs neighbour sensors,
   gaps, impossible values). The simulator must inject such faults sometimes. The dashboard
   shows a sensor-health badge; the assistant uses it to tell "your sensor is probably
   broken" apart from "your water really has a problem" and routes it to the technician or
   the worker.
4. **What-if simulator**: "What if I cut feeding costs by 10 %?" / "What if I add 500 fish
   to Basin 2?" → `simulate_scenario` does the maths in Python, the assistant explains the
   result and the risks (e.g. more fish → more oxygen demand), and shows a before/after chart.
5. **Structured answer cards** (Pydantic-validated JSON output, rendered as UI components):
   - **Risk card**: Low / Medium / High per basin + reasons + actions.
   - **Action plan card**: checklist; each item can become a task through the approval flow.
   - **Comparison card**: table + chart of basins.
6. **Emergency mode**: when a basin hits a critical oxygen level, the assistant panel shows a
   pinned red banner with the oxygen emergency checklist (stop feeding, aerate until after
   sunrise, partial water exchange, call the technician if a sensor fault is suspected),
   with cited sources. The alert itself still comes from the deterministic alert engine.
7. **Proactive insights**: when the ML oxygen-drop probability passes a threshold, show an
   "Insight" card on the dashboard ("Basin 3: high chance of low oxygen before dawn — reduce
   evening feeding, check aerator"), clearly labelled as a prediction.
8. **Multilingual + voice**: answers in French, English or Arabic with proper **RTL layout**
   for Arabic; optional **voice input** with the browser Web Speech API (hidden if the browser
   doesn't support it) — useful for workers in the field.
9. **Export**: download a conversation, a briefing or a risk card as **PDF** (for reports to
   the owner or a bank/insurer).
10. **Smart model routing (optional)**: Haiku by default; a "Deep analysis" toggle uses a
    bigger model set in `LLM_MODEL_DEEP`; the AI Ops page shows the cost difference.

## 9. Phases (do all, in order, testing each)

1. **Inspect + gap analysis**, then foundation: `species` + `species_thresholds`, chemistry
   helpers with tests, `ai_reader` role + `ai` views + RLS + cross-tenant tests,
   `LLMProvider` with anthropic / openai_compat / mock, core tools (`list_basins`,
   `get_basin_status`, `get_readings`).
2. **Copilot**: agent loop, SSE streaming, remaining read tools (incl. oxygen prediction),
   memory tables, the new React panel with chips, charts, data-used chips, stop button.
3. **Grounding**: pgvector, KB markdown + ingestion pipeline, hybrid search, citations.
4. **Quality**: guardrails and limits, golden-set evals + CI, `llm_requests` logging,
   AI Ops page, feedback.
5. **Extras**: approval-gated write tools; optional gated "advanced analytics (beta)" tool
   `run_readonly_query(sql)` validated with SQLGlot (single SELECT on `ai` views only, forced
   LIMIT, no SET), with the executed SQL shown to the user.
6. **Smart features** from section 8b, in the order listed, each one finished and tested
   (with eval cases) before starting the next.
7. **Presentation**: README section for the assistant (features, architecture diagram of the
   assistant flow, eval score table, security design, honest **Limitations** section),
   update `docs/HOW_IT_WORKS.md`, `docs/DECISIONS.md`, screenshots/GIF, verify
   `docker compose up` works **with no API key** (mock mode), then push to `FishFarmFinaleForm`.

## 10. Definition of done

- With no API key: the assistant works in demo mode, using real tools and real data.
- With an Anthropic key: streaming answers, tool steps, inline charts, citations, follow-ups.
- Cross-tenant tests and chemistry tests pass; evals run in CI and scores are in the README.
- AI Ops page shows cost, latency and usage.
- The daily briefing, "Explain this" buttons, sensor-health badges, what-if simulator,
  risk/action cards and emergency mode work, in French, English and Arabic.
- The README shows the eval scores, including the number-grounding rate.
- At the end, give me a short summary: what changed, how to run it, how to add my API key,
  and the GitHub link.
