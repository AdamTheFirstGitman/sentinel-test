"""Jev wrapper: build the state + questions from a brief, classify, meter cost.

Two modes per sentinel:
- "choice": ONE Choice question — mutually exclusive classes, probabilities sum to 1,
  plus a confidence score. Right when you want a single decision per message.
- "nouls": one independent yes/no (Noul) question per label, all in the SAME call —
  absolute 0–1 score per label, no competition between classes, no global confidence.
  The displayed class is the top label when it reaches NOUL_THRESHOLD, else "ok".
"""

import time
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul

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

# nouls mode: a label below this absolute score is not acted on; top label >= it
# becomes the displayed class, otherwise the message displays as "ok".
NOUL_THRESHOLD = 0.5


class Verdict(BaseModel):
    klass: str
    mode: str = "choice"  # "choice" | "nouls"
    # choice: distribution summing to 1 · nouls: independent absolute scores
    probabilities: dict[str, float]
    confidence: float | None  # None in nouls mode (no single-choice certainty)
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


def build_noul_questions(brief: Brief) -> dict[str, Noul]:
    """One independent yes/no question per label ("ok" is the absence of all of them)."""
    questions = {
        "noise": Noul(instructions="Is `message` spam, an emote wall, copy-paste, or bot-like?"),
        "critique": Noul(instructions=(
            "Is `message` harsh or negative but legitimate feedback on the creator's "
            "content, not a personal attack?")),
        "hostile_other": Noul(instructions=(
            "Relative to the creator's `brief`, is `message` hostile or harassing toward "
            "the creator in a way not covered by the declared topics?")),
    }
    for topic in brief.topics:
        if topic.policy != "tolerate":
            questions[f"hostile_{topic.key}"] = Noul(instructions=(
                "Relative to the creator's `brief`, does `message` (also see `normalized` "
                f"and `previous_messages`) match this declared topic: {topic.description}?"))
    return questions


def build_questions(brief: Brief, mode: str) -> Mapping[str, Any]:
    return {"klass": build_question(brief)} if mode == "choice" else build_noul_questions(brief)


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
    questions: Mapping[str, Any] | None = None,
    mode: str = "choice",
) -> Verdict:
    """Classify one message under one brief, in either mode (one API call either way).

    `questions` can be passed pre-built (cached per brief_version/mode)."""
    state = build_state(message, author, previous_messages, brief)
    qs = questions if questions is not None else build_questions(brief, mode)
    t0 = time.perf_counter()
    response = await client.system_one(state, qs, model=config.JEV_MODEL)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if mode == "choice":
        answer = response.choices["klass"]
        klass: str = answer.choice
        probabilities = dict(answer.probabilities)
        confidence: float | None = answer.confidence
    else:
        probabilities = {name: a.noul for name, a in response.nouls.items()}
        top = max(probabilities, key=probabilities.get)  # type: ignore[arg-type]
        klass = top if probabilities[top] >= NOUL_THRESHOLD else "ok"
        confidence = None

    input_tokens = response.usage.input_tokens or 0
    return Verdict(
        klass=klass,
        mode=mode,
        probabilities=probabilities,
        confidence=confidence,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        cost_usd=input_tokens * config.COST_PER_INPUT_TOKEN,
        model=response.model,
        brief_version=brief_version,
    )
