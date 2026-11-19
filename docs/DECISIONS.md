# Decisions

Choices made where the specifications left room, or where they had to be adapted.

## Infrastructure

1. **pgvector locally vs. in Docker.** Docker Compose and CI use `pgvector/pgvector:pg16` (real `vector` type, HNSW index). The development machine has PostgreSQL 18 for Windows without pgvector, and the only Windows build is an unofficial binary, which I chose not to load into the database. The migration therefore checks `pg_available_extensions`: with pgvector it creates `embedding vector(384)` + HNSW; without it, `embedding real[]` and the vector half of the hybrid search runs in Python. The full-text half (GIN + `ts_rank`) and the Reciprocal Rank Fusion are identical in both cases.
2. **Events between processes use PostgreSQL `LISTEN/NOTIFY`.** The simulator/pipeline runs in its own process (its own container). The alert trigger and the ETL call `pg_notify('ff_events', …)`; the API holds one listening connection and forwards each event to the WebSocket clients of the right farm. No Redis needed.
3. **Python 3.12** for the back end (3.11+ required). All dependencies pinned in `backend/requirements.txt`.

## Data

4. **Backfill granularity.** 30 days of history at one reading every 5 minutes per probe (≈104 000 rows). Live readings arrive every 6 s. Charts show 15-minute averages (97 points for 24 h, like the prototype).
5. **Alert de-duplication.** The trigger opens at most one open alert per sensor; repeated out-of-range readings of that sensor do not create new rows until it is resolved. Bulk loads (backfill) set `app.bulk_load = on` so history does not create thousands of alerts; the seed then creates the three demo alerts of the prototype.
6. **Spike rate.** Spikes are applied per simulator tick for the whole farm (one out-of-range reading), never per probe. The brief's 8 % is kept as a stress-test setting (`SIM_SPIKE_PROB=0.08`), but the default is 0.0015 per 6 s tick (about one spike an hour): at 8 % every probe has an open alert within an hour, because alerts are only closed by people, and the real problems disappear in the noise.
7. **Severity** of a trigger alert: oxygen under the species critical level → `critical`; otherwise by distance outside the safe range relative to its width (< 5 % low, < 15 % medium, < 40 % high, else critical).
8. **Demo oxygen baselines.** Basins 1, 2 and 4 got slightly higher oxygen baselines than the prototype (7.2 / 7.0 / 7.0 mg/L) so that, like in the approved design, only the trout basin (Basin 3) regularly dips under its warning level at night. With the prototype values the real alert engine would flag all four basins every night.
9. **pydantic 2.11.7** is pinned: on the development machine Windows Smart App Control blocks the newest `pydantic_core` binary.
10. **Profiles / workers / technicians tables.** The user name lives in `users`, and the role, permissions and shift in `user_roles`, instead of separate `profiles`, `workers` and `technicians` tables with the same columns.

## Front end

11. **Demo team tasks.** The worker's "My tasks" lists tasks assigned to that person; the aerator-cleaning task of the demo is assigned to Karim (worker), so it appears on his Today page (screen 30) and in the technician's maintenance list with his name.
12. **Create-farm copy.** The prototype said a new farm starts with demo basins. The real app starts empty (BUILD_PROMPT §3), so the sentence under the button now says so and points to "Load demo farm".
13. **Team page footnote.** Permissions are pushed over the WebSocket, so the footnote says the member's menu updates instantly instead of "the next time their page refreshes".
14. **AI Ops in the owner menu.** The owner-only AI Ops page required by CHATBOT_UPGRADE.md §8 is a sixth item in the owner's menu (not in the reference screenshots).
15. **"+ Add basin" on the Basins page** (owner only) so a farm can grow after its first basin.
16. **Playwright 1.65.1**: 1.49 can't download browsers on Node 26.

## Machine learning

17. **Model version label.** The saved model is labelled `v1.3` to match the approved design; the label is stored with every prediction.
18. **Reported honestly.** On the simulated farm a persistence baseline ("it dipped last night") scores slightly better than the
    random forest. Both are reported in `ml/README.md`; the model is kept because its features generalise to real farms.

## Assistant

19. **Thinking off on Claude.** With an 800-token output limit, the Anthropic provider sends `thinking: {type: "disabled"}` so the
    budget goes to the answer. A model refusal (`stop_reason: refusal`) is shown as a clear error.
20. **Write tools end the turn.** When the model's only tool calls are write tools, the agent shows the approval cards and ends the turn
    instead of calling the model again.
21. **Briefing.** The overview's "Today's actions" are computed live from the briefing service (cheap and always current); the
    assistant's `get_farm_briefing` caches one briefing per farm and day in `briefings`, with `?refresh=true` to rebuild it.
22. **Proactive insight.** The prediction-driven insight is the first of "Today's actions" ("Cut the Basin 3 evening feed… 62 %
    chance … (estimate)"), so the overview layout stays as approved.
23. **Embeddings.** The default is a deterministic hashing embedder (word + character-trigram feature hashing, 384 dimensions):
    no download, small image, multilingual enough for the short corpus (hit@4 = 1.00). A multilingual sentence-transformers model
    is supported with `EMBEDDING_BACKEND=sentence_transformers` but not installed in the image by default (it adds about 1.5 GB).
24. **DeepEval / RAGAS not used.** The deterministic metrics (tool correctness, hit@k, MRR, refusals, approvals, grounding) are
    implemented in `app/assistant/evals.py` in a few lines with the same definitions, which avoids a heavy dependency in CI.
    Model-judged faithfulness and relevancy need an API key and are not part of CI.
25. **Conversation summary.** Older turns are summarised deterministically (the list of earlier questions) once a conversation
    has more than 16 messages; the last 16 messages are sent in full.
26. **Not built:** the optional `run_readonly_query(sql)` analytics tool (a free-form SQL tool weakens the "trusted tools only"
    design for little demo value) and the optional "Deep analysis" model toggle. Langfuse tracing is not wired; every request is
    already logged in `llm_requests` and shown on the AI Ops page.
27. **PDF export** uses the browser's print dialog with a print stylesheet that keeps only the conversation (no extra PDF library).
28. **Workers and the assistant.** Workers and technicians get a limited assistant: no financial tools, alerts filtered by role, and
    workers cannot create tasks.
