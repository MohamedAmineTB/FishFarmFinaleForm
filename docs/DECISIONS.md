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
