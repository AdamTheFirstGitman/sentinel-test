"""Two independent sentinels (twitch, instagram), each with its own brief, queue,
workers and stats. They share only the Jev client, the SSE fan-out and the budget.
"""

import asyncio
import json
import statistics
import time
from collections import Counter, deque
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice

from app import config
from app.brief import DEFAULT_BRIEFS, Brief
from app.jev import Verdict, build_question, classify

SOURCES = ("twitch", "instagram")


class Sentinel:
    """One source's classifier: own brief, own rate cap, own queue/workers, own stats."""

    def __init__(self, source: str, hub: "Hub") -> None:
        self.source = source
        self.hub = hub
        self.brief: Brief = DEFAULT_BRIEFS[source].model_copy(deep=True)
        self.brief_version = 1
        self.question: Choice = build_question(self.brief)
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self.previous: deque[str] = deque(maxlen=5)
        self.last_text: str | None = None
        self._bucket = float(config.RATE_CAP_PER_S)
        self._bucket_ts = time.monotonic()

        self.seen = 0
        self.classified = 0
        self.dropped = 0
        self.class_counts: Counter[str] = Counter()
        self.latencies: deque[int] = deque(maxlen=500)
        self.seen_times: deque[float] = deque(maxlen=2000)

    # -- intake --------------------------------------------------------------

    def submit(self, author: dict[str, Any], text: str) -> None:
        now = time.time()
        self.seen += 1
        self.seen_times.append(now)
        snapshot = list(self.previous)
        self.previous.append(text)
        self.last_text = text

        if self.hub.paused or not self._take_token() or self.queue.full():
            self.dropped += 1
            return
        self.queue.put_nowait({"author": author, "text": text, "ts": now,
                               "previous_messages": snapshot})

    def _take_token(self) -> bool:
        now = time.monotonic()
        self._bucket = min(config.RATE_CAP_PER_S,
                           self._bucket + (now - self._bucket_ts) * config.RATE_CAP_PER_S)
        self._bucket_ts = now
        if self._bucket >= 1.0:
            self._bucket -= 1.0
            return True
        return False

    # -- classification ------------------------------------------------------

    async def worker(self) -> None:
        while True:
            msg = await self.queue.get()
            try:
                if self.hub.client is None:
                    self.dropped += 1
                    continue
                verdict = await classify(
                    self.hub.client, message=msg["text"], author=msg["author"],
                    previous_messages=msg["previous_messages"],
                    brief=self.brief, brief_version=self.brief_version,
                    question=self.question,
                )
                self._account(verdict)
                self.hub.broadcast({"type": "message", "source": self.source,
                                    "row": {**msg, "source": self.source,
                                            "verdict": verdict.model_dump()}})
            except Exception as exc:  # keep the bench alive on API hiccups
                self.hub.broadcast({"type": "error", "source": self.source,
                                    "detail": type(exc).__name__ + ": " + str(exc)[:300]})

    async def classify_adhoc(self, text: str) -> dict[str, Any]:
        """Direct classification (perturbation tool). Counts cost/budget, not classes."""
        assert self.hub.client is not None
        if self.hub.paused:
            raise RuntimeError("budget exceeded — classification paused")
        verdict = await classify(
            self.hub.client, message=text,
            author={"name": "perturbation-tool", "is_new_to_stream": False, "badges": []},
            previous_messages=list(self.previous),
            brief=self.brief, brief_version=self.brief_version, question=self.question,
        )
        self._account(verdict, count_class=False)
        return verdict.model_dump()

    def _account(self, verdict: Verdict, count_class: bool = True) -> None:
        self.latencies.append(verdict.latency_ms)
        if count_class:
            self.classified += 1
            self.class_counts[verdict.klass] += 1
        self.hub.add_cost(verdict.cost_usd)

    # -- brief ---------------------------------------------------------------

    def apply_brief(self, brief: Brief) -> int:
        self.brief = brief
        self.brief_version += 1
        self.question = build_question(brief)
        self.hub.broadcast({"type": "brief", "source": self.source,
                            "version": self.brief_version, "brief": brief.model_dump()})
        return self.brief_version

    # -- stats ---------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        now = time.time()
        recent = [t for t in self.seen_times if now - t <= 60]
        lat = sorted(self.latencies)
        return {
            "msgs_per_min": len(recent),
            "seen": self.seen,
            "classified": self.classified,
            "dropped": self.dropped,
            "class_counts": dict(self.class_counts),
            "latency_p50": int(statistics.median(lat)) if lat else 0,
            "latency_p95": lat[int(len(lat) * 0.95) - 1] if len(lat) >= 2 else (lat[0] if lat else 0),
            "brief_version": self.brief_version,
            "queue_size": self.queue.qsize(),
        }


class Hub:
    """Shared plumbing: one Jev client, one budget, one SSE fan-out, N sentinels."""

    def __init__(self) -> None:
        self.client: AsyncTypeSafeClient | None = None
        self.cost_usd = 0.0
        self.paused = False
        self.subscribers: set[asyncio.Queue[str]] = set()
        self._tasks: list[asyncio.Task[None]] = []
        self.sentinels: dict[str, Sentinel] = {s: Sentinel(s, self) for s in SOURCES}

    async def start(self) -> None:
        if config.HAS_API_KEY:
            self.client = AsyncTypeSafeClient()
            await self.client.__aenter__()
        for sentinel in self.sentinels.values():
            for _ in range(config.WORKERS):
                self._tasks.append(asyncio.create_task(sentinel.worker()))
        self._tasks.append(asyncio.create_task(self._stats_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self.client is not None:
            await self.client.__aexit__(None, None, None)

    # -- budget --------------------------------------------------------------

    def add_cost(self, cost: float) -> None:
        self.cost_usd += cost
        if not self.paused and self.cost_usd > config.MAX_COST_USD:
            self.paused = True
            self.broadcast({"type": "banner",
                            "text": f"Budget exceeded (${self.cost_usd:.2f} > "
                                    f"${config.MAX_COST_USD:.2f}) — classification paused."})

    # -- fan-out -------------------------------------------------------------

    def broadcast(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        for sub in list(self.subscribers):
            try:
                sub.put_nowait(payload)
            except asyncio.QueueFull:
                self.subscribers.discard(sub)

    def subscribe(self) -> asyncio.Queue[str]:
        sub: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self.subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: asyncio.Queue[str]) -> None:
        self.subscribers.discard(sub)

    # -- stats ---------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "cost_usd": round(self.cost_usd, 6),
            "max_cost_usd": config.MAX_COST_USD,
            "paused": self.paused,
            "sentinels": {source: s.stats() for source, s in self.sentinels.items()},
        }

    async def _stats_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            self.broadcast({"type": "stats", "stats": self.stats()})
