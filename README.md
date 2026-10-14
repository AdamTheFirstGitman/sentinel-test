# sentinel-test

Throwaway test bench to watch **TypeSafe AI's Jev** (System One model) classify
social-media messages in real time against a creator-written *brief*, on two sources:
a live Twitch chat (anonymous, read-only) and an Instagram post's comments
(paste/upload replay, or Graph API behind a flag).

Not production code. Optimised for: works in one afternoon, one screen, easy to
tweak the brief and see the effect immediately.

## Quick start

```bash
cp .env.example .env   # put your TYPESAFE_API_KEY in .env
uv sync
make smoke             # classify 5 hard-coded messages, print probabilities
make dev               # open http://localhost:8000
```

## Smoke test output

_(pending — filled in once `make smoke` has run)_

## Panels

_(filled in as the bench is built)_

## Known limits

_(filled in at the end)_

## Findings

_(to be filled in by hand while using the bench)_
