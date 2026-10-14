"""In-memory pipeline: sources → rate cap → queue → Jev workers → SSE broadcast.

Everything lives in a single Pipeline instance; no database, no persistence
(except labels, handled in app.labels).
"""

import asyncio
import json
import statistics
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice

from app import config
from app.brief import DEFAULT_BRIEF, PRESETS, Brief
from app.jev import Verdict, build_question, classify


@dataclass
class QueuedMessage:
    source: str
    author: dict[str, Any]
    text: str
    ts: float
    previous_messages: list[str]


@dataclass
class Pipeline:
    brief: Brief = field(default_factory=lambda: DEFAULT_BRIEF.model_copy(deep=True))
    brief_version: int = 1
    split_key: str | None = None  # preset key of the second brief, when split mode is on

    def __post_init__(self) -> None:
        self.question: Choice = build_question(self.brief)
        self.split_question: Choice | None = None
        self.queue: asyncio.Queue[QueuedMessage] = asyncio.Queue(maxsize=200)
        self.subscribers: set[asyncio.Queue[str]] = set()
        self.previous: dict[str, deque[str]] = {}
        self.client: AsyncTypeSafeClient | None = None
        self._tasks: list[asyncio.Task[None]] = []

        # Rate cap: simple token bucket.
        self._bucket = float(config.RATE_CAP_PER_S)
        self._bucket_ts = time.monotonic()

        # Stats
        self.seen = 0
        self.classified = 0
        self.dropped = 0
        self.paused = False
        self.cost_usd = 0.0
        self.class_counts: Counter[str] = Counter()
        self.latencies: deque[int] = deque(maxlen=500)
        self.seen_times: deque[float] = deque(maxlen=2000)
        self.last_message: QueuedMessage | None = None

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if config.HAS_API_KEY:
            self.client = AsyncTypeSafeClient()
            await self.client.__aenter__()
        for _ in range(config.WORKERS):
            self._tasks.append(asyncio.create_task(self._worker()))
        self._tasks.append(asyncio.create_task(self._stats_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self.client is not None:
            await self.client.__aexit__(None, None, None)

    # -- intake ------------------------------------------------------------

    def submit(self, source: str, author: dict[str, Any], text: str) -> None:
        """Called by sources for every incoming message. Never blocks."""
        now = time.time()
        self.seen += 1
        self.seen_times.append(now)
        prev = self.previous.setdefault(source, deque(maxlen=5))
        snapshot = list(prev)
        prev.append(text)

        if self.paused or not self._take_token() or self.queue.full():
            self.dropped += 1
            return
        msg = QueuedMessage(source=source, author=author, text=text, ts=now,
                            previous_messages=snapshot)
        self.last_message = msg
        self.queue.put_nowait(msg)

    def _take_token(self) -> bool:
        now = time.monotonic()
        self._bucket = min(config.RATE_CAP_PER_S,
                           self._bucket + (now - self._bucket_ts) * config.RATE_CAP_PER_S)
        self._bucket_ts = now
        if self._bucket >= 1.0:
            self._bucket -= 1.0
            return True
        return False

    # -- classification ----------------------------------------------------

    async def _worker(self) -> None:
        while True:
            msg = await self.queue.get()
            try:
                if self.client is None:
                    self.dropped += 1
                    continue
                row = await self._classify_message(msg)
                self.broadcast({"type": "message", "row": row})
            except Exception as exc:  # keep the bench alive on API hiccups
                self.broadcast({"type": "error", "detail": type(exc).__name__ + ": " + str(exc)[:300]})

    async def _classify_message(self, msg: QueuedMessage) -> dict[str, Any]:
        assert self.client is not None
        verdict = await classify(
            self.client, message=msg.text, author=msg.author,
            previous_messages=msg.previous_messages,
            brief=self.brief, brief_version=self.brief_version, question=self.question,
        )
        self._account(verdict)

        split_verdict: Verdict | None = None
        if self.split_key is not None and not self.paused:
            split_verdict = await classify(
                self.client, message=msg.text, author=msg.author,
                previous_messages=msg.previous_messages,
                brief=PRESETS[self.split_key], brief_version=self.brief_version,
                question=self.split_question,
            )
            self._account(split_verdict, count_class=False)

        return {
            "source": msg.source,
            "ts": msg.ts,
            "author": msg.author,
            "text": msg.text,
            "previous_messages": msg.previous_messages,
            "verdict": verdict.model_dump(),
            "split": split_verdict.model_dump() if split_verdict else None,
            "split_key": self.split_key,
        }

    def _account(self, verdict: Verdict, count_class: bool = True) -> None:
        self.cost_usd += verdict.cost_usd
        self.latencies.append(verdict.latency_ms)
        if count_class:
            self.classified += 1
            self.class_counts[verdict.klass] += 1
        if not self.paused and self.cost_usd > config.MAX_COST_USD:
            self.paused = True
            self.broadcast({"type": "banner",
                            "text": f"Budget exceeded (${self.cost_usd:.2f} > "
                                    f"${config.MAX_COST_USD:.2f}) — classification paused."})

    async def classify_adhoc(self, text: str, source: str = "adhoc") -> dict[str, Any]:
        """Direct classification (perturbation tool). Bypasses the queue, counts cost/budget."""
        assert self.client is not None
        if self.paused:
            raise RuntimeError("budget exceeded — classification paused")
        verdict = await classify(
            self.client, message=text,
            author={"name": "perturbation-tool", "is_new_to_stream": False, "badges": []},
            previous_messages=list(self.previous.get(source, [])),
            brief=self.brief, brief_version=self.brief_version, question=self.question,
        )
        self._account(verdict, count_class=False)
        return verdict.model_dump()

    # -- brief / split -----------------------------------------------------

    def apply_brief(self, brief: Brief) -> int:
        self.brief = brief
        self.brief_version += 1
        self.question = build_question(brief)
        self.broadcast({"type": "brief", "version": self.brief_version,
                        "brief": brief.model_dump()})
        return self.brief_version

    def set_split(self, preset_key: str | None) -> None:
        self.split_key = preset_key
        self.split_question = build_question(PRESETS[preset_key]) if preset_key else None

    # -- fan-out -----------------------------------------------------------

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

    # -- stats -------------------------------------------------------------

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
            "cost_usd": round(self.cost_usd, 6),
            "max_cost_usd": config.MAX_COST_USD,
            "paused": self.paused,
            "brief_version": self.brief_version,
            "queue_size": self.queue.qsize(),
        }

    async def _stats_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            self.broadcast({"type": "stats", "stats": self.stats()})
