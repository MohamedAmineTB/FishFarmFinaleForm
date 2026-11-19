"""Realtime: PostgreSQL LISTEN/NOTIFY -> WebSocket clients of the right farm.

Every process (API, simulator/pipeline, SQL trigger) publishes with pg_notify('ff_events', json).
The API keeps one listening connection in a background thread and forwards each event to
the WebSocket clients whose farm (owner_id) matches. Clients never receive another farm's events.
"""

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict

import psycopg
from fastapi import WebSocket

from .config import get_settings

log = logging.getLogger("fishfarm.events")


class Hub:
    def __init__(self) -> None:
        self.clients: dict[str, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()

    def add(self, owner_id: str, ws: WebSocket) -> None:
        self.clients[owner_id].add(ws)

    def remove(self, owner_id: str, ws: WebSocket) -> None:
        self.clients[owner_id].discard(ws)

    async def broadcast(self, event: dict) -> None:
        owner = event.get("owner_id")
        if not owner:
            return
        dead = []
        for ws in list(self.clients.get(owner, ())):
            try:
                await ws.send_json(event)
            except Exception:  # client went away
                dead.append(ws)
        for ws in dead:
            self.remove(owner, ws)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        threading.Thread(target=self._listen_forever, name="pg-listen", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _listen_forever(self) -> None:
        dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
        while not self._stop.is_set():
            try:
                with psycopg.connect(dsn, autocommit=True) as conn:
                    conn.execute("LISTEN ff_events")
                    log.info("listening for ff_events")
                    while not self._stop.is_set():
                        for n in conn.notifies(timeout=1.0):
                            try:
                                event = json.loads(n.payload)
                            except json.JSONDecodeError:
                                continue
                            if self.loop:
                                asyncio.run_coroutine_threadsafe(self.broadcast(event), self.loop)
            except Exception as e:  # database restarted: retry
                log.warning("listener error: %s; retrying in 2 s", e)
                time.sleep(2)


hub = Hub()
