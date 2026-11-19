"""FastAPI application: REST API under /api, WebSocket at /ws."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import SessionLocal
from .deps import load_ctx
from .events import hub
from .routers import alerts, auth, basins, farm, reports, team, work
from .security import decode_access_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.start(asyncio.get_running_loop())
    yield
    hub.stop()


app = FastAPI(
    title="FishFarm API",
    version="1.0.0",
    lifespan=lifespan,
    description="Fish-farm monitoring: basins, live readings, alerts, team, reports, ML and assistant.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, farm, basins, alerts, reports, team, work):
    app.include_router(r.router)


def _include_optional() -> None:
    """Routers added in later phases (assistant, AI Ops) register themselves here when present."""
    try:
        from .routers import assistant

        app.include_router(assistant.router)
    except ImportError:
        pass


_include_optional()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket, token: str = ""):
    try:
        data = decode_access_token(token)
    except jwt.InvalidTokenError:
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    try:
        ctx = load_ctx(db, uuid.UUID(data["sub"]))
    finally:
        db.close()
    if ctx is None:
        await websocket.close(code=4401)
        return
    owner = str(ctx.owner_id)
    await websocket.accept()
    hub.add(owner, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(owner, websocket)
