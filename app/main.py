"""FastAPI wiring: one page, one SSE stream, small JSON endpoints."""

import asyncio
import contextlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import config
from app.brief import PRESETS, Brief, Topic
from app.pipeline import Pipeline
from app.twitch import TwitchSource

pipeline = Pipeline()
twitch = TwitchSource(pipeline)

STATIC = Path(__file__).parent / "static"


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await pipeline.start()
    yield
    await twitch.part()
    await pipeline.stop()


app = FastAPI(title="sentinel-test", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/snapshot")
async def snapshot() -> dict:
    return {
        "stats": pipeline.stats(),
        "brief": pipeline.brief.model_dump(),
        "brief_version": pipeline.brief_version,
        "split_key": pipeline.split_key,
        "presets": {key: brief.model_dump() for key, brief in PRESETS.items()},
        "twitch": {"status": twitch.status, "channel": twitch.channel},
        "ig_graph_enabled": config.IG_GRAPH_ENABLED,
        "model": config.JEV_MODEL,
        "api_key_missing": not config.HAS_API_KEY,
    }


@app.get("/events")
async def events() -> StreamingResponse:
    sub = pipeline.subscribe()

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'stats', 'stats': pipeline.stats()})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(sub.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            pipeline.unsubscribe(sub)

    return StreamingResponse(stream(), media_type="text/event-stream")


class JoinRequest(BaseModel):
    channel: str


@app.post("/twitch/join")
async def twitch_join(req: JoinRequest) -> dict:
    await twitch.join(req.channel)
    return {"ok": True, "channel": twitch.channel}


@app.post("/twitch/part")
async def twitch_part() -> dict:
    await twitch.part()
    return {"ok": True}


class BriefRequest(BaseModel):
    name: str = "custom"
    creator_context: str
    topics: list[Topic]


@app.post("/brief/apply")
async def brief_apply(req: BriefRequest) -> dict:
    version = pipeline.apply_brief(Brief(**req.model_dump()))
    return {"ok": True, "brief_version": version}


class SplitRequest(BaseModel):
    preset_key: str | None = None


@app.post("/split")
async def split(req: SplitRequest) -> dict:
    if req.preset_key is not None and req.preset_key not in PRESETS:
        return {"ok": False, "error": "unknown preset"}
    pipeline.set_split(req.preset_key)
    return {"ok": True, "split_key": pipeline.split_key}
