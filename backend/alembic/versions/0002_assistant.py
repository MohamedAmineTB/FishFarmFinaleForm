"""Assistant: memory, knowledge base (pgvector when available), logs, feedback, briefings,
read-only role `ai_reader`, row-level security and the `ai` schema of views.

Revision ID: 0002_assistant
"""

from sqlalchemy import text

from alembic import op

revision = "0002_assistant"
down_revision = "0001_core"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "basins",
    "sensors",
    "readings",
    "hourly_stats",
    "alerts",
    "maintenance",
    "reports",
    "tasks",
    "predictions",
    "user_roles",
]

TABLES = r"""
-- the correct UF/IFAS fact sheet for dissolved oxygen is FA002 (FA031 is about ammonia)
UPDATE species_thresholds SET source_label = replace(source_label, 'FA031', 'FA002'),
  source_url = 'https://edis.ifas.ufl.edu/publication/FA002' WHERE source_url LIKE '%FA031%';

CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title varchar(120) NOT NULL DEFAULT 'New conversation',
  summary text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_conversations_user ON conversations(user_id, updated_at DESC);

CREATE TABLE messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  owner_user_id uuid NOT NULL,
  role varchar(12) NOT NULL CHECK (role IN ('user','assistant','tool')),
  content jsonb NOT NULL,
  tokens_in integer NOT NULL DEFAULT 0,
  tokens_out integer NOT NULL DEFAULT 0,
  model varchar(60),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_messages_conv ON messages(conversation_id, created_at);

CREATE TABLE kb_documents (
  id varchar(60) PRIMARY KEY,
  title varchar(200) NOT NULL,
  url varchar(400) NOT NULL,
  publisher varchar(120) NOT NULL,
  year integer,
  licence varchar(120),
  species varchar(40),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE kb_chunks (
  id serial PRIMARY KEY,
  doc_id varchar(60) NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  section varchar(200) NOT NULL,
  content text NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(section, '') || ' ' || content)) STORED
);
CREATE INDEX ix_kb_chunks_tsv ON kb_chunks USING gin(tsv);

CREATE TABLE llm_requests (
  id bigserial PRIMARY KEY,
  owner_user_id uuid NOT NULL,
  user_id uuid,
  conversation_id uuid,
  message_id uuid,
  provider varchar(30) NOT NULL,
  model varchar(60) NOT NULL,
  prompt_version varchar(20) NOT NULL,
  latency_ms integer NOT NULL,
  tokens_in integer NOT NULL DEFAULT 0,
  tokens_out integer NOT NULL DEFAULT 0,
  cost_usd double precision NOT NULL DEFAULT 0,
  tools jsonb NOT NULL DEFAULT '[]'::jsonb,
  retrieved jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'ok',
  feedback smallint,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_llm_requests_owner ON llm_requests(owner_user_id, created_at DESC);
CREATE INDEX ix_llm_requests_user ON llm_requests(user_id, created_at DESC);

CREATE TABLE llm_usage (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day date NOT NULL,
  requests integer NOT NULL DEFAULT 0,
  tokens integer NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);

CREATE TABLE feedback (
  id bigserial PRIMARY KEY,
  owner_user_id uuid NOT NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  rating smallint NOT NULL CHECK (rating IN (-1, 1)),
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, message_id)
);

CREATE TABLE briefings (
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day date NOT NULL,
  content jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, day)
);

-- actions proposed by the assistant, executed only after the user clicks Approve
CREATE TABLE pending_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  message_id uuid,
  tool varchar(40) NOT NULL,
  args jsonb NOT NULL,
  status varchar(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','cancelled')),
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""

AI_VIEWS = r"""
CREATE SCHEMA ai;
CREATE VIEW ai.basins WITH (security_invoker = true) AS
  SELECT id, owner_user_id, name, species, capacity, fish_count, status, revenue, feeding_cost, maintenance_cost,
         operational_cost, position FROM public.basins;
CREATE VIEW ai.sensors WITH (security_invoker = true) AS
  SELECT id, owner_user_id, basin_id, code, type, status, min_value, max_value, last_value, last_reading_at,
         last_calibrated_at, health, health_note FROM public.sensors;
CREATE VIEW ai.readings WITH (security_invoker = true) AS
  SELECT owner_user_id, sensor_id, value, recorded_at FROM public.readings;
CREATE VIEW ai.hourly_stats WITH (security_invoker = true) AS SELECT * FROM public.hourly_stats;
CREATE VIEW ai.alerts WITH (security_invoker = true) AS
  SELECT id, owner_user_id, basin_id, sensor_id, kind, metric, type, title, description, severity, value,
         is_resolved, resolved_at, resolution_note, created_at FROM public.alerts;
CREATE VIEW ai.maintenance WITH (security_invoker = true) AS SELECT * FROM public.maintenance;
CREATE VIEW ai.reports WITH (security_invoker = true) AS
  SELECT id, owner_user_id, kind, title, body, basin_id, generated_at FROM public.reports;
CREATE VIEW ai.tasks WITH (security_invoker = true) AS
  SELECT id, owner_user_id, title, assignee_user_id, basin_id, sensor_id, status, source, due_date, created_at
  FROM public.tasks;
CREATE VIEW ai.predictions WITH (security_invoker = true) AS SELECT * FROM public.predictions;
CREATE VIEW ai.team WITH (security_invoker = true) AS
  SELECT r.user_id, r.owner_user_id, u.name, r.role, r.shift_start, r.shift_end
  FROM public.user_roles r JOIN public.users u ON u.id = r.user_id;
CREATE VIEW ai.species_thresholds AS SELECT * FROM public.species_thresholds;
"""


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(TABLES)
    has_vector = bind.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).first() is not None
    if has_vector:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE kb_chunks ADD COLUMN embedding vector(384)")
        op.execute("CREATE INDEX ix_kb_chunks_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops)")
        # hybrid search: full text + vector similarity, merged with Reciprocal Rank Fusion (k = 50)
        op.execute(r"""
CREATE FUNCTION kb_hybrid_search(q text, q_emb vector(384), k integer DEFAULT 5, p_species text DEFAULT NULL)
RETURNS TABLE (chunk_id integer, doc_id varchar, score double precision) LANGUAGE sql STABLE AS $$
  WITH fts AS (
    SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, to_tsquery('simple', q)) DESC) AS r
    FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id
    WHERE c.tsv @@ to_tsquery('simple', q) AND (p_species IS NULL OR d.species IS NULL OR d.species = p_species)
    LIMIT 50),
  vec AS (
    SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> q_emb) AS r
    FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id
    WHERE p_species IS NULL OR d.species IS NULL OR d.species = p_species
    ORDER BY c.embedding <=> q_emb LIMIT 50)
  SELECT c.id, c.doc_id, coalesce(1.0 / (50 + fts.r), 0) + coalesce(1.0 / (50 + vec.r), 0) AS score
  FROM kb_chunks c LEFT JOIN fts ON fts.id = c.id LEFT JOIN vec ON vec.id = c.id
  WHERE fts.id IS NOT NULL OR vec.id IS NOT NULL
  ORDER BY score DESC LIMIT k
$$;""")
    else:
        # PostgreSQL without pgvector (local Windows development): same column as a float array,
        # the vector half of the hybrid search runs in Python (see app/assistant/rag.py)
        op.execute("ALTER TABLE kb_chunks ADD COLUMN embedding real[]")

    op.execute(AI_VIEWS)
    # read-only role for the assistant's tools (the API switches to it with SET LOCAL ROLE)
    op.execute("""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_reader') THEN
    CREATE ROLE ai_reader NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;""")
    op.execute("GRANT ai_reader TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA ai TO ai_reader")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA ai TO ai_reader")
    # security_invoker views check the caller's rights on the base tables: grant SELECT there too,
    # rows are then limited by the RLS policies below (users: only id and name, never password hashes)
    for t in TENANT_TABLES + ["species_thresholds"]:
        op.execute(f"GRANT SELECT ON public.{t} TO ai_reader")
    op.execute("GRANT SELECT (id, name) ON public.users TO ai_reader")
    op.execute("GRANT USAGE ON SCHEMA public TO ai_reader")
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY tenant_ai ON public.{t} FOR SELECT TO ai_reader
            USING (owner_user_id = nullif(current_setting('app.owner_id', true), '')::uuid)""")
    op.execute("ALTER ROLE ai_reader SET statement_timeout = '15s'")


def downgrade() -> None:
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_ai ON public.{t}")
        op.execute(f"ALTER TABLE public.{t} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP SCHEMA IF EXISTS ai CASCADE")
    op.execute("DROP FUNCTION IF EXISTS kb_hybrid_search")
    for t in (
        "pending_actions",
        "briefings",
        "feedback",
        "llm_usage",
        "llm_requests",
        "kb_chunks",
        "kb_documents",
        "messages",
        "conversations",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ai_reader")
