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

**Left — sources & brief.**
- *Twitch*: type a channel name, Join/Leave. Connects anonymously (`justinfan…`) over
  IRC WebSocket, read-only, no key. Every chat message goes through the classifier.
- *Instagram*: paste comments one per line (`author: text`, or bare text), or pick a
  JSON/CSV export (`author,text`), set a rate (msgs/s) and Replay. If `IG_ACCESS_TOKEN`
  and `IG_MEDIA_ID` are set in `.env`, a "Fetch via Graph API" button appears and
  replays the post's real comments (paginated GET, never writes).
- *Brief*: preset dropdown (FR streamer / EN gaming streamer / IG fitness creator),
  editable creator context and topics (key / label / description / policy). **Apply
  brief** bumps `brief_version` and rebuilds the Jev question: one `choice` question
  with fixed classes `ok`, `noise`, `critique`, `hostile_other` plus one
  `hostile_<key>` per topic whose policy isn't `tolerate`.

**Centre — live feed.** Newest on top: time, author (+badges, "new" for first-msg),
text, class pill, stacked probability bar, confidence / latency / cost / brief
version. Filter chips: all, hostile only, grey zone (confidence < 0.6). The *split*
toggle classifies every message under a second preset brief too and shows both
verdicts. Each row has an "I'd have said" control that appends your disagreement to
`data/labels.jsonl`.

**Right — stats & tools.** Live msgs/min, classified/dropped counts, queue depth,
class distribution, latency p50/p95, cumulative cost vs `MAX_COST_USD`, brief
version. The perturbation tool re-classifies the last (or a typed) message under
leetspeak, homoglyphs, spaced letters and trailing emojis.

## Budget & safety

- Hard stop: when cumulative cost exceeds `MAX_COST_USD` (default $2.00),
  classification pauses and a banner shows. Restart the server to reset.
- Rate cap: max 20 msg/s sent to Jev; anything above is dropped and counted.
- Read-only by construction: the only things ever sent to Twitch are the IRC
  handshake and PONGs; the only Instagram call is a paginated GET.
- `.env` is gitignored; keys never appear in logs or in the UI.

## Known limits

- Everything is in memory: restart loses stats, feed, brief edits and budget state.
- `.env` is read at startup only — adding the key or changing `MAX_COST_USD` needs a
  restart (uvicorn `--reload` does not watch `.env`).
- One Twitch channel at a time; joining another leaves the first.
- Split mode doubles cost per message (two full API calls, both metered).
- The feed keeps the last 200 rows; the latency percentiles use the last 500 calls.
- Plain JS + SSE instead of HTMX: fewer moving parts for JSON-driven rows.
- The brief editor trusts you: empty keys/descriptions are silently dropped, no
  validation beyond that.

## Findings

_(to be filled in by hand while using the bench)_

- Early observation from the perturbation tool: heavy leetspeak/homoglyphs keep the
  right class but drop confidence into the grey zone (~0.6), and spacing letters out
  can flip between two applicable hostile topics.
