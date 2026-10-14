"""Instagram comments: paste/upload replay through the pipeline, plus a read-only
Graph API fetch behind the IG_ACCESS_TOKEN/IG_MEDIA_ID feature flag.

Nothing is ever written to Instagram; the only HTTP call is a paginated GET.
"""

import asyncio
import csv
import io
import json
from typing import Any

import httpx

from app import config
from app.pipeline import Pipeline

GRAPH_URL = "https://graph.facebook.com/v21.0"


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


async def fetch_graph_comments(limit: int = 500) -> list[dict[str, str]]:
    """Paginate GET /{media-id}/comments. Requires the feature flag env vars."""
    if not config.IG_GRAPH_ENABLED:
        raise RuntimeError("IG_ACCESS_TOKEN / IG_MEDIA_ID not set")
    comments: list[dict[str, str]] = []
    url = f"{GRAPH_URL}/{config.IG_MEDIA_ID}/comments"
    params: dict[str, Any] = {
        "fields": "id,text,username,timestamp",
        "limit": 50,
        "access_token": config.IG_ACCESS_TOKEN,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        while url and len(comments) < limit:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            for c in payload.get("data", []):
                if c.get("text"):
                    comments.append({"author": c.get("username", "unknown"), "text": c["text"]})
            url = payload.get("paging", {}).get("next")
            params = None  # the `next` URL already carries the query string
    return comments


class InstagramReplayer:
    """Replays a list of comments through the pipeline at a chosen rate (msgs/s)."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
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

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self, comments: list[dict[str, str]], rate: float) -> None:
        for comment in comments:
            self.pipeline.submit(
                "instagram",
                {"name": comment["author"], "is_new_to_stream": False, "badges": []},
                comment["text"],
            )
            self.sent += 1
            await asyncio.sleep(1.0 / rate)
        self.pipeline.broadcast({"type": "instagram", "status": "finished",
                                 "sent": self.sent, "total": self.total})
