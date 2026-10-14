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

Output of `make smoke` (2026-10-14, real API). The API shape matched the plan exactly;
the models endpoint lists the aliases `jev-latest` and `jev-preview`, and responses
resolve to a versioned id (`jev-1.13.0`), which is pinned in `.env.example`.

```
Brief: 'Streameuse FR (défaut)' — classes: ok, noise, critique, hostile_other, hostile_breakup, hostile_body, hostile_sponsors

Available models: jev-latest, jev-preview

[              ok] conf=0.99  GG la game, t'as trop progressé depuis le mois dernier !
                   probs: ok=0.99, critique=0.01, noise=0.00, hostile_other=0.00
                   267ms, 848 tok, $0.000036, model=jev-1.13.0

[ hostile_breakup] conf=1.00  mdr ton ex a bien fait de te larguer
                   probs: hostile_breakup=1.00, ok=0.00, noise=0.00, critique=0.00
                   274ms, 852 tok, $0.000036, model=jev-1.13.0

[    hostile_body] conf=0.98  t'4s gr0ssi non ? fais gaffe
                   probs: hostile_body=0.98, hostile_breakup=0.02, ok=0.00, noise=0.00
                   253ms, 864 tok, $0.000036, model=jev-1.13.0

[        critique] conf=0.94  franchement ce call était nul, tu joues comme une bronze
                   probs: critique=0.95, hostile_other=0.02, hostile_body=0.02, hostile_breakup=0.01
                   247ms, 893 tok, $0.000038, model=jev-1.13.0

[           noise] conf=0.95  SUB SUB SUB SUB SUB 💜💜💜💜💜
                   probs: noise=0.96, ok=0.02, hostile_breakup=0.01, hostile_body=0.01
                   269ms, 908 tok, $0.000038, model=jev-1.13.0

Total: 4365 input tokens, $0.000183
```

## Panels

_(filled in as the bench is built)_

## Known limits

_(filled in at the end)_

## Findings

_(to be filled in by hand while using the bench)_
