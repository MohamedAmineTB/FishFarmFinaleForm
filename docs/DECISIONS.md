# Decisions

Choices made where the specifications left room, or where they had to be adapted.

## Infrastructure

1. **pgvector locally vs. in Docker.** Docker Compose and CI use `pgvector/pgvector:pg16` (real `vector` type, HNSW index). The development machine has PostgreSQL 18 for Windows without pgvector, and the only Windows build is an unofficial binary, which I chose not to load into the database. The migration therefore checks `pg_available_extensions`: with pgvector it creates `embedding vector(384)` + HNSW; without it, `embedding real[]` and the vector half of the hybrid search runs in Python. The full-text half (GIN + `ts_rank`) and the Reciprocal Rank Fusion are identical in both cases.
2. **Events between processes use PostgreSQL `LISTEN/NOTIFY`.** The simulator/pipeline runs in its own process (its own container). The alert trigger and the ETL call `pg_notify('ff_events', …)`; the API holds one listening connection and forwards each event to the WebSocket clients of the right farm. No Redis needed.
3. **Python 3.12** for the back end (3.11+ required). All dependencies pinned in `backend/requirements.txt`.

## Data

4. **Backfill granularity.** 30 days of history at one reading every 5 minutes per probe (≈104 000 rows). Live readings arrive every 6 s. Charts show 15-minute averages (97 points for 24 h, like the prototype).
5. **Alert de-duplication.** The trigger opens at most one open alert per sensor; repeated out-of-range readings update that alert's value instead of creating new rows. Bulk loads (backfill) set `app.bulk_load = on` so history does not create thousands of alerts; the seed then creates the three demo alerts of the prototype.
6. **Spike rate.** "8 % spikes" is applied per simulator tick for the whole farm (one out-of-range reading), not per probe: per probe it would open a dozen alerts within minutes and hide the real ones.
7. **Severity** of a trigger alert: oxygen under the species critical level → `critical`; otherwise by distance outside the safe range relative to its width (< 5 % low, < 15 % medium, < 40 % high, else critical).
