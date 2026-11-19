"""Core schema: enums, tables, indexes, species thresholds, alert trigger.

Revision ID: 0001_core
"""

from alembic import op

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE app_role AS ENUM ('owner','worker','technician');
CREATE TYPE basin_status AS ENUM ('healthy','warning','critical','inactive');
CREATE TYPE sensor_type AS ENUM ('temperature','ph','oxygen');
CREATE TYPE sensor_status AS ENUM ('active','inactive','maintenance');
CREATE TYPE alert_severity AS ENUM ('low','medium','high','critical');
CREATE TYPE task_status AS ENUM ('pending','in_progress','fixed');

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email varchar(320) NOT NULL UNIQUE,
  password_hash varchar(100) NOT NULL,
  name varchar(120) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE owners (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  farm_name varchar(120) NOT NULL,
  company_name varchar(160) NOT NULL,
  country varchar(80) NOT NULL,
  timezone varchar(64) NOT NULL DEFAULT 'Europe/Paris',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- one row per user: their role and which farm (owner) they belong to
CREATE TABLE user_roles (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role app_role NOT NULL,
  permissions jsonb NOT NULL DEFAULT '{}'::jsonb,
  shift_start varchar(5),
  shift_end varchar(5),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_user_roles_owner ON user_roles(owner_user_id);

CREATE TABLE refresh_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash varchar(64) NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE species_thresholds (
  id serial PRIMARY KEY,
  species varchar(40) NOT NULL,
  metric varchar(20) NOT NULL,
  unit varchar(10) NOT NULL,
  optimal_min double precision, optimal_max double precision,
  warning_min double precision, warning_max double precision,
  critical_min double precision, critical_max double precision,
  emergency_min double precision,
  source_label varchar(160) NOT NULL,
  source_url varchar(400) NOT NULL,
  verified boolean NOT NULL DEFAULT false,
  note text,
  UNIQUE (species, metric)
);

CREATE TABLE basins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name varchar(80) NOT NULL,
  species varchar(40) NOT NULL CHECK (species IN ('tilapia','rainbow_trout','common_carp','sea_bass','sea_bream','atlantic_salmon')),
  capacity double precision NOT NULL CHECK (capacity > 0),
  fish_count integer NOT NULL CHECK (fish_count >= 0),
  status basin_status NOT NULL DEFAULT 'healthy',
  revenue double precision NOT NULL DEFAULT 0,
  feeding_cost double precision NOT NULL DEFAULT 0,
  maintenance_cost double precision NOT NULL DEFAULT 0,
  operational_cost double precision NOT NULL DEFAULT 0,
  sim_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  position integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_basins_owner ON basins(owner_user_id);

CREATE TABLE sensors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  basin_id uuid NOT NULL REFERENCES basins(id) ON DELETE CASCADE,
  code varchar(12) NOT NULL,
  type sensor_type NOT NULL,
  status sensor_status NOT NULL DEFAULT 'active',
  min_value double precision,
  max_value double precision,
  last_value double precision,
  last_reading_at timestamptz,
  last_calibrated_at timestamptz,
  health varchar(12) NOT NULL DEFAULT 'ok' CHECK (health IN ('ok','stuck','drift','spiky','offline')),
  health_note text,
  sim_fault jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, code)
);
CREATE INDEX ix_sensors_basin ON sensors(basin_id);

CREATE TABLE readings (
  id bigserial PRIMARY KEY,
  owner_user_id uuid NOT NULL,
  sensor_id uuid NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
  value double precision NOT NULL,
  recorded_at timestamptz NOT NULL
);
CREATE INDEX ix_readings_sensor_time ON readings(sensor_id, recorded_at);

-- hourly aggregates built by the batch job (used by charts and ML features)
CREATE TABLE hourly_stats (
  sensor_id uuid NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
  hour timestamptz NOT NULL,
  owner_user_id uuid NOT NULL,
  basin_id uuid NOT NULL,
  metric sensor_type NOT NULL,
  min_value double precision NOT NULL,
  max_value double precision NOT NULL,
  mean_value double precision NOT NULL,
  n integer NOT NULL,
  PRIMARY KEY (sensor_id, hour)
);
CREATE INDEX ix_hourly_basin ON hourly_stats(basin_id, hour);

CREATE TABLE alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  basin_id uuid NOT NULL REFERENCES basins(id) ON DELETE CASCADE,
  sensor_id uuid REFERENCES sensors(id) ON DELETE SET NULL,
  kind varchar(10) NOT NULL CHECK (kind IN ('water','sensor')),
  metric varchar(20) NOT NULL,
  type varchar(40) NOT NULL,
  title varchar(160) NOT NULL,
  description text NOT NULL,
  severity alert_severity NOT NULL,
  value double precision,
  is_resolved boolean NOT NULL DEFAULT false,
  resolved_by uuid REFERENCES users(id) ON DELETE SET NULL,
  resolved_at timestamptz,
  resolution_note text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_alerts_owner_open ON alerts(owner_user_id, is_resolved, created_at DESC);

CREATE TABLE maintenance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  technician_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  sensor_id uuid REFERENCES sensors(id) ON DELETE SET NULL,
  work_type varchar(20) NOT NULL,
  description text NOT NULL,
  due_date date,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  author_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  kind varchar(12) NOT NULL CHECK (kind IN ('shift','maintenance')),
  title varchar(200) NOT NULL,
  body text NOT NULL,
  basin_id uuid REFERENCES basins(id) ON DELETE SET NULL,
  content jsonb NOT NULL DEFAULT '{}'::jsonb,
  generated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_reports_owner ON reports(owner_user_id, generated_at DESC);

CREATE TABLE report_reads (
  report_id uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  read_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (report_id, user_id)
);

CREATE TABLE tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL,
  title varchar(200) NOT NULL,
  description text,
  assignee_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  basin_id uuid REFERENCES basins(id) ON DELETE SET NULL,
  sensor_id uuid REFERENCES sensors(id) ON DELETE SET NULL,
  status task_status NOT NULL DEFAULT 'pending',
  source varchar(12) NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','assistant','maintenance')),
  due_date date,
  due_label varchar(40),
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_tasks_owner ON tasks(owner_user_id);

CREATE TABLE simulator_state (
  owner_user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  paused boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE etl_runs (
  id bigserial PRIMARY KEY,
  started_at timestamptz NOT NULL DEFAULT now(),
  source varchar(20) NOT NULL,
  received integer NOT NULL,
  accepted integer NOT NULL,
  rejected integer NOT NULL,
  reasons jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE predictions (
  id bigserial PRIMARY KEY,
  owner_user_id uuid NOT NULL,
  basin_id uuid NOT NULL REFERENCES basins(id) ON DELETE CASCADE,
  probability double precision NOT NULL,
  horizon varchar(40) NOT NULL,
  features jsonb NOT NULL,
  top_features jsonb NOT NULL,
  model_version varchar(20) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_predictions_basin ON predictions(basin_id, created_at DESC);
"""

THRESHOLDS = r"""
INSERT INTO species_thresholds
 (species, metric, unit, optimal_min, optimal_max, warning_min, warning_max, critical_min, critical_max, emergency_min, source_label, source_url, verified, note) VALUES
 ('tilapia','oxygen','mg/L', NULL, NULL, 5, NULL, 3, NULL, 2,
  'UF/IFAS FA031 · Dissolved oxygen','https://edis.ifas.ufl.edu/publication/FA031', false,
  'Warm-water cut-offs (warning 5, critical 3, emergency 2 mg/L) are design choices. FAO notes Nile tilapia tolerates DO below 1 ppm for short periods.'),
 ('tilapia','temperature','°C', 31, 36, 22, 34, NULL, 36, NULL,
  'FAO · Nile tilapia fact sheet','https://www.fao.org/fishery/en/culturedspecies/oreochromis_niloticus', true,
  'FAO: prefers 31–36 °C. The 22–34 °C alert band is the farm''s operating range.'),
 ('tilapia','ph','pH', NULL, NULL, 6.5, 8.5, NULL, NULL, NULL,
  'FAO · Water quality in aquaculture','https://www.fao.org/fishery/en/culturedspecies/oreochromis_niloticus', false, NULL),
 ('rainbow_trout','oxygen','mg/L', NULL, NULL, 7, NULL, 5, NULL, 4,
  'OMAFRA 2024 · Rainbow trout profile','https://www.ontario.ca/page/rainbow-trout', false,
  'OMAFRA: DO 80–100 % of saturation. The mg/L cut-offs are design choices derived from it.'),
 ('rainbow_trout','oxygen_saturation','%', 80, 100, 80, NULL, 60, NULL, 40,
  'OMAFRA 2024 · Rainbow trout profile','https://www.ontario.ca/page/rainbow-trout', true,
  'Salmonid saturation cut-offs (warning 80 %, critical 60 %, emergency 40 %) are design choices.'),
 ('rainbow_trout','temperature','°C', 13, 18, 4, 20, NULL, 24, NULL,
  'OMAFRA 2024 · Rainbow trout profile','https://www.ontario.ca/page/rainbow-trout', true,
  'Optimal 13–18 °C (OMAFRA); FAO: best below 21 °C. Sources differ on upper tolerance (24 vs 27 °C): the conservative 24 °C is kept.'),
 ('rainbow_trout','ph','pH', 7, 8, 6.5, 8.5, NULL, NULL, NULL,
  'FAO · Rainbow trout fact sheet','https://www.fao.org/fishery/en/culturedspecies/oncorhynchus_mykiss', true, 'OMAFRA optimal 7–8; FAO 6.5–8.5.'),
 ('common_carp','oxygen','mg/L', NULL, NULL, 5, NULL, 3, NULL, 2,
  'UF/IFAS FA031 · Dissolved oxygen','https://edis.ifas.ufl.edu/publication/FA031', false,
  'Generic warm-water cut-offs. FAO: common carp tolerates DO down to 0.3–0.5 mg/L.'),
 ('common_carp','temperature','°C', 23, 30, 15, 32, NULL, 34, NULL,
  'FAO · Common carp fact sheet','https://www.fao.org/fishery/en/culturedspecies/cyprinus_carpio', true, 'Optimal growth 23–30 °C (FAO).'),
 ('common_carp','ph','pH', NULL, NULL, 6.5, 9, NULL, NULL, NULL,
  'FAO · Common carp fact sheet','https://www.fao.org/fishery/en/culturedspecies/cyprinus_carpio', true, NULL),
 ('atlantic_salmon','oxygen_saturation','%', NULL, NULL, 70, NULL, 60, NULL, 39,
  'Stehfest et al. 2017 · Scientific Reports','https://www.nature.com/srep/', true,
  'Growth reduction below 70 % saturation, stress below 60 %, critical below 39 %.'),
 ('atlantic_salmon','oxygen','mg/L', NULL, NULL, 7, NULL, 5.5, NULL, 3.5,
  'Stehfest et al. 2017 · Scientific Reports','https://www.nature.com/srep/', false, 'mg/L values derived from the saturation limits at about 12 °C.'),
 ('atlantic_salmon','temperature','°C', 12, 17, 4, 20, NULL, 22, NULL,
  'Stehfest et al. 2017 · Scientific Reports','https://www.nature.com/srep/', true, 'Prefers about 17 °C and avoids water above 20 °C.'),
 ('atlantic_salmon','ph','pH', NULL, NULL, 6.5, 8.5, NULL, NULL, NULL,
  'FAO · Water quality in aquaculture','https://www.fao.org/fishery/en/', false, NULL),
 ('sea_bass','oxygen','mg/L', NULL, NULL, 5, NULL, 3, NULL, 2,
  'Generic warm-water default (UF/IFAS FA031)','https://edis.ifas.ufl.edu/publication/FA031', false,
  'No verified species values yet: generic warm-water oxygen cut-offs only, no temperature or pH alerts.'),
 ('sea_bream','oxygen','mg/L', NULL, NULL, 5, NULL, 3, NULL, 2,
  'Generic warm-water default (UF/IFAS FA031)','https://edis.ifas.ufl.edu/publication/FA031', false,
  'No verified species values yet: generic warm-water oxygen cut-offs only, no temperature or pH alerts.');
"""

FUNCTIONS = r"""
-- Display name of a species code
CREATE FUNCTION ff_species_name(sp text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE sp WHEN 'tilapia' THEN 'Nile tilapia' WHEN 'rainbow_trout' THEN 'Rainbow trout'
    WHEN 'common_carp' THEN 'Common carp' WHEN 'sea_bass' THEN 'European sea bass'
    WHEN 'sea_bream' THEN 'Gilthead sea bream' WHEN 'atlantic_salmon' THEN 'Atlantic salmon' ELSE sp END
$$;

-- Number without useless trailing zeros (20 -> '20', 8.5 -> '8.5'); oxygen thresholds keep one decimal
CREATE FUNCTION ff_num(v double precision, keep_one boolean DEFAULT false) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN keep_one THEN to_char(round(v::numeric, 1), 'FM9990.0') ELSE trim_scale(round(v::numeric, 1))::text END
$$;

-- Basin status from the latest probe values, the species thresholds and open alerts (DESIGN_SPEC §5)
CREATE FUNCTION ff_basin_status(p_basin uuid) RETURNS basin_status LANGUAGE plpgsql STABLE AS $$
DECLARE
  sp text; v_do double precision; v_t double precision; v_ph double precision;
  o species_thresholds; t species_thresholds; p species_thresholds;
BEGIN
  SELECT species INTO sp FROM basins WHERE id = p_basin;
  SELECT last_value INTO v_do FROM sensors WHERE basin_id = p_basin AND type = 'oxygen' LIMIT 1;
  SELECT last_value INTO v_t  FROM sensors WHERE basin_id = p_basin AND type = 'temperature' LIMIT 1;
  SELECT last_value INTO v_ph FROM sensors WHERE basin_id = p_basin AND type = 'ph' LIMIT 1;
  SELECT * INTO o FROM species_thresholds WHERE species = sp AND metric = 'oxygen';
  SELECT * INTO t FROM species_thresholds WHERE species = sp AND metric = 'temperature';
  SELECT * INTO p FROM species_thresholds WHERE species = sp AND metric = 'ph';
  IF (v_do < o.critical_min) OR (v_t > t.warning_max + 2) THEN RETURN 'critical'; END IF;
  IF (v_do < o.warning_min) OR (v_ph > p.warning_max) OR (v_ph < p.warning_min)
     OR (v_t > t.warning_max) OR (v_t < t.warning_min) THEN RETURN 'warning'; END IF;
  IF EXISTS (SELECT 1 FROM alerts WHERE basin_id = p_basin AND NOT is_resolved AND severity <> 'low') THEN
    RETURN 'warning';
  END IF;
  RETURN 'healthy';
END $$;

-- Recompute and store a basin's status; returns true when it changed
CREATE FUNCTION ff_refresh_basin_status(p_basin uuid) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE st basin_status; old basin_status;
BEGIN
  SELECT status INTO old FROM basins WHERE id = p_basin;
  IF old = 'inactive' THEN RETURN false; END IF;
  st := ff_basin_status(p_basin);
  IF st IS DISTINCT FROM old THEN
    UPDATE basins SET status = st, updated_at = now() WHERE id = p_basin;
    RETURN true;
  END IF;
  RETURN false;
END $$;

-- THE ALERT ENGINE: runs for every new reading.
-- 1. stores the latest value on the sensor
-- 2. compares the value with the sensor's safe range (min_value / max_value, from the species thresholds)
-- 3. opens an alert (one open alert per sensor at most) with a severity based on how far out of range it is
-- 4. recalculates the basin status and notifies the API (WebSocket) through pg_notify
CREATE FUNCTION ff_evaluate_reading(p_sensor uuid, p_value double precision, p_at timestamptz)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
  s sensors; b basins; thr species_thresholds;
  out_low boolean; out_high boolean; width double precision; dist double precision;
  sev alert_severity; ttl text; descr text; metric_label text; species_label text; unit text;
  existing uuid; new_id uuid;
BEGIN
  SELECT * INTO s FROM sensors WHERE id = p_sensor;
  IF s.last_reading_at IS NULL OR p_at >= s.last_reading_at THEN
    UPDATE sensors SET last_value = p_value, last_reading_at = p_at WHERE id = s.id;
  END IF;

  out_low  := s.min_value IS NOT NULL AND p_value < s.min_value;
  out_high := s.max_value IS NOT NULL AND p_value > s.max_value;

  IF out_low OR out_high THEN
    SELECT id INTO existing FROM alerts
      WHERE sensor_id = s.id AND kind = 'water' AND NOT is_resolved LIMIT 1;
    IF existing IS NULL THEN
      SELECT * INTO b FROM basins WHERE id = s.basin_id;
      SELECT * INTO thr FROM species_thresholds WHERE species = b.species AND metric = s.type::text;
      species_label := lower(ff_species_name(b.species));
      IF s.type = 'ph' THEN species_label := ff_species_name(b.species); END IF;

      width := greatest(coalesce(s.max_value, s.min_value * 2) - coalesce(s.min_value, 0), 0.0001);
      dist := CASE WHEN out_low THEN s.min_value - p_value ELSE p_value - s.max_value END;
      sev := CASE
        WHEN s.type = 'oxygen' AND thr.critical_min IS NOT NULL AND p_value < thr.critical_min THEN 'critical'
        WHEN dist / width < 0.05 THEN 'low'
        WHEN dist / width < 0.15 THEN 'medium'
        WHEN dist / width < 0.40 THEN 'high'
        ELSE 'critical' END;

      IF s.type = 'oxygen' THEN
        ttl := 'Oxygen below ' || ff_num(s.min_value, true) || ' mg/L';
        descr := 'Dissolved oxygen fell to ' || to_char(p_value::numeric, 'FM990.00') || ' mg/L, under the '
          || ff_num(s.min_value, true) || ' mg/L warning level for ' || lower(ff_species_name(b.species)) || '.';
      ELSIF s.type = 'ph' THEN
        IF out_high THEN
          ttl := 'pH above ' || ff_num(s.max_value);
          descr := 'pH reached ' || to_char(p_value::numeric, 'FM990.00') || ', above the ' || ff_num(s.max_value)
            || ' limit for ' || ff_species_name(b.species) || '.';
        ELSE
          ttl := 'pH below ' || ff_num(s.min_value);
          descr := 'pH fell to ' || to_char(p_value::numeric, 'FM990.00') || ', below the ' || ff_num(s.min_value)
            || ' limit for ' || ff_species_name(b.species) || '.';
        END IF;
      ELSE
        IF out_high THEN
          ttl := 'Temperature above ' || ff_num(s.max_value) || ' °C';
          descr := 'Water temperature reached ' || to_char(p_value::numeric, 'FM990.0') || ' °C, above the '
            || ff_num(s.max_value) || ' °C limit for ' || lower(ff_species_name(b.species)) || '.';
        ELSE
          ttl := 'Temperature below ' || ff_num(s.min_value) || ' °C';
          descr := 'Water temperature fell to ' || to_char(p_value::numeric, 'FM990.0') || ' °C, below the '
            || ff_num(s.min_value) || ' °C limit for ' || lower(ff_species_name(b.species)) || '.';
        END IF;
      END IF;

      INSERT INTO alerts (owner_user_id, basin_id, sensor_id, kind, metric, type, title, description, severity, value, created_at)
      VALUES (s.owner_user_id, s.basin_id, s.id, 'water', s.type::text,
              CASE WHEN out_low THEN 'below_range' ELSE 'above_range' END, ttl, descr, sev, p_value, p_at)
      RETURNING id INTO new_id;

      PERFORM pg_notify('ff_events', json_build_object(
        'type', 'alert', 'action', 'created', 'owner_id', s.owner_user_id, 'alert_id', new_id,
        'basin_id', s.basin_id, 'kind', 'water', 'title', ttl, 'severity', sev, 'basin_name', b.name)::text);
    END IF;
  END IF;

  PERFORM ff_refresh_basin_status(s.basin_id);
  RETURN new_id;
END $$;

CREATE FUNCTION ff_on_reading() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- bulk loads (30-day backfill) skip the engine; the loader sets last values itself
  IF coalesce(current_setting('app.bulk_load', true), '') = 'on' THEN
    RETURN NEW;
  END IF;
  PERFORM ff_evaluate_reading(NEW.sensor_id, NEW.value, NEW.recorded_at);
  RETURN NEW;
END $$;

CREATE TRIGGER trg_readings_alert AFTER INSERT ON readings
  FOR EACH ROW EXECUTE FUNCTION ff_on_reading();
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(THRESHOLDS)
    op.execute(FUNCTIONS)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_readings_alert ON readings")
    for fn in (
        "ff_on_reading()",
        "ff_evaluate_reading(uuid, double precision, timestamptz)",
        "ff_refresh_basin_status(uuid)",
        "ff_basin_status(uuid)",
        "ff_num(double precision, boolean)",
        "ff_species_name(text)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for t in (
        "predictions",
        "etl_runs",
        "simulator_state",
        "tasks",
        "report_reads",
        "reports",
        "maintenance",
        "alerts",
        "hourly_stats",
        "readings",
        "sensors",
        "basins",
        "species_thresholds",
        "refresh_tokens",
        "user_roles",
        "owners",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for e in ("task_status", "alert_severity", "sensor_status", "sensor_type", "basin_status", "app_role"):
        op.execute(f"DROP TYPE IF EXISTS {e}")
