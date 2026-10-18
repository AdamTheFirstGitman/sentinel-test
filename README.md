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

## Two sentinels

Twitch and Instagram are **two fully independent sentinels**, each on its own tab:
separate brief (own version counter), separate queue/workers/rate cap, separate feed
and stats. They share only the Jev client and the global budget (top-right of the
header). The default briefs are deliberately generic one-liners — add your own
context and topics per source from the UI.

Each tab has the same three columns:

**Left — source & brief.**
- *Twitch tab*: type a channel name, Join/Leave. Connects anonymously (`justinfan…`)
  over IRC WebSocket, read-only, no key. Every chat message goes through that
  sentinel.
- *Instagram tab*: paste a **post URL** and Load — with `IG_ACCESS_TOKEN` in `.env`,
  the post is resolved against the connected account's own media and its comments are
  fetched (paginated GET, never writes) then replayed at the chosen rate. Without a
  token, the fold-out paste/upload mode still works: one comment per line
  (`author: text`, or bare text) or a JSON/CSV export (`author,text`).
- *Brief*: editable creator context and topics (key / label / description / policy),
  per source. **Apply brief** bumps that sentinel's `brief_version` and rebuilds its
  Jev questions.

**Classification modes** (selector in the feed header, per sentinel; one API call
per message either way, same cost):
- *choice — one class*: a single `choice` question with the fixed classes `ok`,
  `noise`, `critique`, `hostile_other` plus one `hostile_<key>` per non-tolerated
  topic. Classes are mutually exclusive (probabilities sum to 1) and come with a
  `confidence` score. Right when you want one decision per message.
- *multi-label — score per label*: one independent `noul` (yes/no) question per
  label in the same call. Each label gets an absolute 0–1 score; several can fire
  at once and ambiguity reads as "everything low" instead of a flat distribution.
  The displayed class is the top label when it reaches 0.5, else `ok`; there is no
  confidence score. Grey-zone filter = top score in [0.3, 0.6).

**Centre — live feed** (per source). Newest on top: time, author (+badges, "new" for
first-msg), text, class pill, stacked probability bar, confidence / latency / cost /
brief version. Filter chips: all, hostile only, grey zone (confidence < 0.6). Each
row has an "I'd have said" control that appends your disagreement to
`data/labels.jsonl`.

**Right — stats & tools** (per source). Live msgs/min, classified/dropped counts,
queue depth, class distribution, latency p50/p95, brief version. The perturbation
tool classifies that sentinel's last (or a typed) message as a baseline, plus 4
variants — leetspeak, homoglyphs and spaced letters are deterministic; the trailing
emoji tail is deliberately re-sampled each run, since emoji choice measurably shifts
the model — 5 API calls. Each card shows the full per-class probability breakdown,
not just the winner. Perturbation runs use an empty chat context so they are
comparable; the remaining run-to-run variation is the model's own stochasticity.

## Budget & safety

- Hard stop: when cumulative cost exceeds `MAX_COST_USD` (default $2.00),
  classification pauses and a banner shows. Restart the server to reset.
- Rate cap: max 20 msg/s sent to Jev; anything above is dropped and counted.
- Read-only by construction: the only things ever sent to Twitch are the IRC
  handshake and PONGs; the only Instagram call is a paginated GET.
- `.env` is gitignored; keys never appear in logs or in the UI.

## Known limits

- Everything is in memory: restart loses stats, feeds, brief edits and budget state.
- `.env` is read at startup only — adding the key or changing `MAX_COST_USD` needs a
  restart (uvicorn `--reload` does not watch `.env`).
- One Twitch channel at a time; joining another leaves the first.
- Instagram URL mode only finds posts of the **connected account** (it matches the
  URL against `/me/media` permalinks — the Graph API cannot read arbitrary posts).
- Each feed keeps the last 200 rows; latency percentiles use the last 500 calls.
- Plain JS + SSE instead of HTMX: fewer moving parts for JSON-driven rows.
- The brief editor trusts you: empty keys/descriptions are silently dropped, no
  validation beyond that.
- Jev is not deterministic: identical requests move per-class probabilities by
  roughly ±5 points, enough to flip the displayed label when two classes are
  near-tied (that's what the grey-zone filter is for).

## Findings

_(to be filled in by hand while using the bench)_

- Early observation from the perturbation tool: heavy leetspeak/homoglyphs keep the
  right class but drop confidence into the grey zone (~0.6), and spacing letters out
  can flip between two applicable hostile topics.
- Measured (4 identical calls on a borderline dogwhistle, 2026-10-18): probabilities
  vary ±5 points run to run, e.g. ok 0.49–0.59 vs hostile 0.39–0.49 on the same
  input — the label is a coin flip there. Implicit references the model has to
  "get" (e.g. naming a person as an insinuation) sit near 50/50; explicit tropes
  land solidly in the topic class.
