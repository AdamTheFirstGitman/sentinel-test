"""Instagram comments, read-only: paste/upload replay, or fetch a post's comments
from its URL via the Graph API (needs IG_ACCESS_TOKEN in .env).

URL mode resolves the post by listing the account's own media and matching the
permalink shortcode — so it works for posts on the connected account. Nothing is
ever written to Instagram; the only HTTP calls are paginated GETs.
"""

import asyncio
import csv
import io
import json
import re
from typing import Any

import httpx

from app import config
from app.pipeline import Hub

_SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")


def parse_paste(text: str) -> list[dict[str, str]]:
    """One comment per line; 'author: text' when a colon is present, else anonymous."""
    comments = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        author, sep, body = line.partition(":")
        if sep and 0 < len(author) <= 30 and " " not in author.strip():
            comments.append({"author": author.strip(), "text": body.strip()})
        else:
            comments.append({"author": "anonymous", "text": line})
    return comments


def parse_upload(filename: str, content: bytes) -> list[dict[str, str]]:
    """JSON (list of {author, text}) or CSV with author,text columns."""
    text = content.decode("utf-8", errors="replace")
    if filename.lower().endswith(".json"):
        data = json.loads(text)
        return [{"author": str(c.get("author", "anonymous")), "text": str(c.get("text", ""))}
                for c in data if c.get("text")]
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{"author": (row.get("author") or "anonymous").strip(),
             "text": (row.get("text") or "").strip()}
            for row in rows if (row.get("text") or "").strip()]


def shortcode_from_url(url: str) -> str | None:
    match = _SHORTCODE_RE.search(url)
    return match.group(1) if match else None


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None) -> dict:
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        try:
            detail = response.json()["error"]["message"]
        except Exception:
            detail = response.text[:200]
        raise RuntimeError(f"Graph API {response.status_code}: {detail}")
    return response.json()


async def resolve_media_id(url: str) -> str:
    """Post URL (or raw numeric id) → media id, by matching the account's media permalinks."""
    url = url.strip()
    if url.isdigit():
        return url
    shortcode = shortcode_from_url(url)
    if not shortcode:
        raise RuntimeError("not an Instagram post URL (expected …instagram.com/p/<code>/ or /reel/…)")
    needle = f"/{shortcode}/"
    endpoint = f"{config.IG_GRAPH_HOST}/{config.IG_USER_ID}/media"
    params: dict[str, Any] | None = {"fields": "id,permalink", "limit": 100,
                                     "access_token": config.IG_ACCESS_TOKEN}
    async with httpx.AsyncClient(timeout=20) as client:
        for _ in range(10):  # up to ~1000 most recent posts
            payload = await _get(client, endpoint, params)
            for media in payload.get("data", []):
                if needle in media.get("permalink", ""):
                    return media["id"]
            endpoint = payload.get("paging", {}).get("next")
            params = None  # the `next` URL already carries the query string
            if not endpoint:
                break
    raise RuntimeError("post not found in the connected account's media "
                       "(URL mode only works for your own posts)")


async def fetch_comments(media_id: str, limit: int = 500) -> list[dict[str, str]]:
    """Paginate GET /{media-id}/comments."""
    comments: list[dict[str, str]] = []
    endpoint = f"{config.IG_GRAPH_HOST}/{media_id}/comments"
    params: dict[str, Any] | None = {"fields": "id,text,username,timestamp", "limit": 50,
                                     "access_token": config.IG_ACCESS_TOKEN}
    async with httpx.AsyncClient(timeout=20) as client:
        while endpoint and len(comments) < limit:
            payload = await _get(client, endpoint, params)
            for c in payload.get("data", []):
                if c.get("text"):
                    comments.append({"author": c.get("username", "unknown"), "text": c["text"]})
            endpoint = payload.get("paging", {}).get("next")
            params = None
    return comments


async def fetch_comments_for_url(url: str) -> list[dict[str, str]]:
    if not config.IG_GRAPH_ENABLED:
        raise RuntimeError("IG_ACCESS_TOKEN not set in .env — paste comments instead, "
                           "or add a token and restart")
    media_id = await resolve_media_id(url)
    return await fetch_comments(media_id)


class InstagramReplayer:
    """Replays a list of comments through the instagram sentinel at a chosen rate (msgs/s)."""

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self._task: asyncio.Task[None] | None = None
        self.total = 0
        self.sent = 0

    def start(self, comments: list[dict[str, str]], rate: float) -> None:
        self.stop()
        self.total = len(comments)
        self.sent = 0
        self._task = asyncio.create_task(self._run(comments, max(0.1, min(rate, 20.0))))

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self, comments: list[dict[str, str]], rate: float) -> None:
        sentinel = self.hub.sentinels["instagram"]
        for comment in comments:
            sentinel.submit({"name": comment["author"], "is_new_to_stream": False,
                             "badges": []}, comment["text"])
            self.sent += 1
            await asyncio.sleep(1.0 / rate)
        self.hub.broadcast({"type": "instagram", "status": "finished",
                            "sent": self.sent, "total": self.total})
