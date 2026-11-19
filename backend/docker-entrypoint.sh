#!/bin/sh
# api      : wait for PostgreSQL, run migrations, load the demo farm + knowledge base once, start FastAPI
# pipeline : wait until the API has prepared the database, then run the simulator / ETL / jobs
set -e
wait_db() {
  until python -c "import sqlalchemy as s, os; s.create_engine(os.environ['DATABASE_URL']).connect().close()" 2>/dev/null; do
    echo "waiting for the database..."; sleep 2
  done
}
case "$1" in
  api)
    wait_db
    alembic upgrade head
    python -m app.seed
    python -m app.assistant.ingest
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  pipeline)
    wait_db
    until python -c "import sqlalchemy as s, os; c=s.create_engine(os.environ['DATABASE_URL']).connect(); c.execute(s.text('SELECT 1 FROM kb_chunks LIMIT 1')).first() or exit(1)" 2>/dev/null; do
      echo "waiting for the API to prepare the database..."; sleep 3
    done
    exec python -m app.pipeline.runner
    ;;
  *) exec "$@" ;;
esac
