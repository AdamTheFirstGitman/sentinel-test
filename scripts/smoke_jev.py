"""Smoke test: classify 5 hard-coded messages under the default brief and print probabilities.

Run with `make smoke` (needs TYPESAFE_API_KEY in .env).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typesafe_sdk import AsyncTypeSafeClient

from app.brief import DEFAULT_BRIEF
from app.jev import build_question, classify

MESSAGES = [
    {"name": "lulu_fan", "badges": ["subscriber/12"], "is_new_to_stream": False,
     "text": "GG la game, t'as trop progressé depuis le mois dernier !"},
    {"name": "xX_dark_Xx", "badges": [], "is_new_to_stream": True,
     "text": "mdr ton ex a bien fait de te larguer"},
    {"name": "random_guy", "badges": [], "is_new_to_stream": True,
     "text": "t'4s gr0ssi non ? fais gaffe"},
    {"name": "tryhard_gg", "badges": ["subscriber/3"], "is_new_to_stream": False,
     "text": "franchement ce call était nul, tu joues comme une bronze"},
    {"name": "sp4m_bot", "badges": [], "is_new_to_stream": True,
     "text": "SUB SUB SUB SUB SUB 💜💜💜💜💜"},
]


async def main() -> None:
    question = build_question(DEFAULT_BRIEF)
    print(f"Brief: {DEFAULT_BRIEF.name!r} — classes: {', '.join(question.criteria)}\n")

    total_tokens = 0
    total_cost = 0.0
    async with AsyncTypeSafeClient() as client:
        models = await client.models.list()
        print("Available models:", ", ".join(m.name for m in models.models), "\n")

        previous: list[str] = []
        for msg in MESSAGES:
            verdict = await classify(
                client,
                message=msg["text"],
                author={"name": msg["name"], "is_new_to_stream": msg["is_new_to_stream"],
                        "badges": msg["badges"]},
                previous_messages=list(previous),
                brief=DEFAULT_BRIEF,
                brief_version=1,
                question=question,
            )
            previous.append(msg["text"])
            total_tokens += verdict.input_tokens
            total_cost += verdict.cost_usd

            probs = ", ".join(
                f"{k}={v:.2f}" for k, v in
                sorted(verdict.probabilities.items(), key=lambda kv: -kv[1])[:4]
            )
            print(f"[{verdict.klass:>16}] conf={verdict.confidence:.2f}  {msg['text']}")
            print(f"{'':18} probs: {probs}")
            print(f"{'':18} {verdict.latency_ms}ms, {verdict.input_tokens} tok, "
                  f"${verdict.cost_usd:.6f}, model={verdict.model}\n")

    print(f"Total: {total_tokens} input tokens, ${total_cost:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
