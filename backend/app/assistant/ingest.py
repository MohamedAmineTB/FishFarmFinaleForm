"""Knowledge-base ingestion pipeline: `python -m app.assistant.ingest` (parse kb/*.md -> chunk -> embed -> load)."""

from ..db import session_scope
from .rag import ingest


def main() -> None:
    with session_scope() as db:
        print(ingest(db))


if __name__ == "__main__":
    main()
