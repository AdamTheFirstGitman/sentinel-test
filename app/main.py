"""FastAPI wiring: one page, one SSE stream, small JSON endpoints — all source-scoped."""

import asyncio
import contextlib
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import config
from app.brief import Brief, Topic
from app.instagram import InstagramReplayer, fetch_comments_for_url, parse_paste, parse_upload
from app.labels import append_label
from app.perturb import PERTURBATIONS
from app.pipeline import SOURCES, Hub
from app.twitch import TwitchSource

hub = Hub()
twitch = TwitchSource(hub)
instagram = InstagramReplayer(hub)

STATIC = Path(__file__).parent / "static"


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await hub.start()
    yield
    await twitch.part()
    instagram.stop()
    await hub.stop()


app = FastAPI(title="sentinel-test", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/snapshot")
async def snapshot() -> dict:
    return {
        "stats": hub.stats(),
        "briefs": {source: {"brief": s.brief.model_dump(), "version": s.brief_version}
                   for source, s in hub.sentinels.items()},
        "twitch": {"status": twitch.status, "channel": twitch.channel},
        "ig_graph_enabled": config.IG_GRAPH_ENABLED,
        "model": config.JEV_MODEL,
        "api_key_missing": not config.HAS_API_KEY,
    }


@app.get("/events")
async def events() -> StreamingResponse:
    sub = hub.subscribe()

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'stats', 'stats': hub.stats()})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(sub.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(sub)

    return StreamingResponse(stream(), media_type="text/event-stream")


# -- twitch -------------------------------------------------------------------

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


# -- instagram ----------------------------------------------------------------

class ReplayRequest(BaseModel):
    text: str = ""           # paste mode: one comment per line
    filename: str = ""       # upload mode: file read client-side
    content: str = ""
    rate: float = 2.0


@app.post("/instagram/replay")
async def instagram_replay(req: ReplayRequest) -> dict:
    if req.filename:
        comments = parse_upload(req.filename, req.content.encode())
    else:
        comments = parse_paste(req.text)
    if not comments:
        return {"ok": False, "error": "no comments parsed"}
    instagram.start(comments, req.rate)
    return {"ok": True, "total": len(comments)}


class FetchUrlRequest(BaseModel):
    url: str
    rate: float = 2.0


@app.post("/instagram/fetch_url")
async def instagram_fetch_url(req: FetchUrlRequest) -> dict:
    try:
        comments = await fetch_comments_for_url(req.url)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    if not comments:
        return {"ok": False, "error": "no comments on this post"}
    instagram.start(comments, req.rate)
    return {"ok": True, "total": len(comments)}


@app.post("/instagram/stop")
async def instagram_stop() -> dict:
    instagram.stop()
    return {"ok": True}


# -- per-source brief / tools ---------------------------------------------------

class BriefRequest(BaseModel):
    source: str
    name: str = "custom"
    creator_context: str
    topics: list[Topic]


@app.post("/brief/apply")
async def brief_apply(req: BriefRequest) -> dict:
    if req.source not in SOURCES:
        return {"ok": False, "error": "unknown source"}
    version = hub.sentinels[req.source].apply_brief(
        Brief(name=req.name, creator_context=req.creator_context, topics=req.topics))
    return {"ok": True, "brief_version": version}


class PerturbRequest(BaseModel):
    source: str
    text: str = ""  # empty = last message seen by that sentinel


@app.post("/perturb")
async def perturb(req: PerturbRequest) -> dict:
    if req.source not in SOURCES:
        return {"ok": False, "error": "unknown source"}
    sentinel = hub.sentinels[req.source]
    text = req.text.strip() or (sentinel.last_text or "")
    if not text:
        return {"ok": False, "error": "no message to perturb yet"}
    results = []
    try:
        for name, fn in PERTURBATIONS.items():
            variant = fn(text)
            verdict = await sentinel.classify_adhoc(variant)
            results.append({"name": name, "text": variant, "verdict": verdict})
    except RuntimeError as exc:  # budget pause
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "original": text, "results": results}


class LabelRequest(BaseModel):
    source: str
    text: str
    previous_messages: list[str]
    brief_version: int
    jev_class: str
    my_class: str


@app.post("/label")
async def label(req: LabelRequest) -> dict:
    append_label(req.model_dump())
    return {"ok": True}
