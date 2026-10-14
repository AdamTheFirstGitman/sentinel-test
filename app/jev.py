"""Jev wrapper: build the state + single Choice question from a brief, classify, meter cost."""

import time
from typing import Any

from pydantic import BaseModel
from typesafe_sdk import AsyncTypeSafeClient, Choice

from app import config
from app.brief import Brief
from app.perturb import normalize

FIXED_CLASSES: dict[str, str] = {
    "ok": "harmless, supportive, neutral chat",
    "noise": "spam, emote walls, copy-paste, bot-like",
    "critique": "harsh or negative but legitimate feedback on the content, not a personal attack",
    "hostile_other": "hostile or harassing but not about a declared topic",
}

INSTRUCTIONS = (
    "Relative to the creator's `brief`, classify `message` (also see `normalized` "
    "and `previous_messages`). Pick the single best class."
)


class Verdict(BaseModel):
    klass: str
    probabilities: dict[str, float]
    confidence: float
    latency_ms: int
    input_tokens: int
    cost_usd: float
    model: str
    brief_version: int


def build_question(brief: Brief) -> Choice:
    """One Choice question: the 4 fixed classes plus hostile_<key> per non-tolerated topic."""
    criteria = dict(FIXED_CLASSES)
    for topic in brief.topics:
        if topic.policy != "tolerate":
            criteria[f"hostile_{topic.key}"] = topic.description
    return Choice(instructions=INSTRUCTIONS, criteria=criteria)


def build_state(
    message: str,
    author: dict[str, Any],
    previous_messages: list[str],
    brief: Brief,
) -> dict[str, Any]:
    return {
        "message": message,
        "normalized": normalize(message),
        "previous_messages": previous_messages,
        "author": author,
        "brief": {
            "creator_context": brief.creator_context,
            "topics": [t.model_dump() for t in brief.topics],
        },
    }


async def classify(
    client: AsyncTypeSafeClient,
    *,
    message: str,
    author: dict[str, Any],
    previous_messages: list[str],
    brief: Brief,
    brief_version: int,
    question: Choice | None = None,
) -> Verdict:
    """Classify one message under one brief. `question` can be passed pre-built (cached per brief_version)."""
    state = build_state(message, author, previous_messages, brief)
    q = question or build_question(brief)
    t0 = time.perf_counter()
    response = await client.system_one(state, {"klass": q}, model=config.JEV_MODEL)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    answer = response.choices["klass"]
    input_tokens = response.usage.input_tokens or 0
    return Verdict(
        klass=answer.choice,
        probabilities=dict(answer.probabilities),
        confidence=answer.confidence,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        cost_usd=input_tokens * config.COST_PER_INPUT_TOKEN,
        model=response.model,
        brief_version=brief_version,
    )
