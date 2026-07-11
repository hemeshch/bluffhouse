# Demo recording script (~4½ minutes)

A scene-by-scene guide for recording the bluffhouse demo video. Everything
runs locally, needs **no API keys**, and is deterministic — you can retake
any scene and get the identical game.

## Setup (before recording)

```sh
cd bluffhouse
uv sync && uv run pytest -q        # confidence check: 93 passed
open demos/presentation.html        # the deck, full-screen it (⌃⌘F in most browsers)
uv run bluffhouse demo --no-open    # pre-generate the demo run
uv run bluffhouse serve --no-open   # hub on http://127.0.0.1:8484 in a second terminal
```

Recording: QuickTime (File → New Screen Recording) or Loom, 1080p or
better, system audio off, mic on. Hide bookmarks bar and notifications
(macOS: ⌥-click Notification Center → enable Do Not Disturb).

---

## Scene 1 — the pitch (deck slides 1–3, ~60s)

Full-screen the deck. Advance with →.

> "Every LLM benchmark we use is solitaire — one model, alone, against a
> static task. But the agents we're deploying negotiate, persuade, and get
> manipulated. bluffhouse measures that. It's a poker table for language
> models — the chips are the cover story. The real game is seven
> communication channels: whispers that leak, gestures that carry secret
> codes, notes, public accusations. And the core trick —" *(slide 4)* "—
> the environment records one objective truth, while every agent lives in
> its own subjective slice of it. Every lie is recorded next to the
> sender's private intent. No human labels, no LLM judges in the loop."

Optionally hit slides 5–6 in one breath: attention is a scarce budget;
nobody — not even the environment — referees the truth of an accusation.

## Scene 2 — the live drama (~2 min)

Switch to the terminal, run (it re-generates and opens instantly):

```sh
uv run bluffhouse demo
```

The replay opens. Now the money sequence:

1. **Ground truth first.** Hand 1, press ▶ (or → to step). Pause on the
   whisper bubble:
   > "Grok whispers a collusion deal to GPT. Watch the feed — ground truth
   > shows the words, the *private intent* — 'set up a collusion deal with GPT' —
   > and the reception ledger: GPT received it, **Claude caught a
   > fragment at 42% confidence**, Llama missed it entirely."
2. **Switch POV → Claude.** Step back over the same moment:
   > "Here's the same moment from Claude's chair: just a shredded
   > fragment — '…fold… big… pots… me.…'. Claude was spending 80% of its
   > attention watching Grok. That's the attention economy paying off."
3. **The accusation.** Step to the flop:
   > "Claude converts that fragment into a public accusation. Nobody
   > fact-checks it — it lands only as hard as the table believes it.
   > Watch the heat meters on the nameplates."
4. **Switch POV → Llama**, scrub back to hand 1:
   > "And from Llama's seat? The whisper never existed. Missed events
   > aren't marked — they're simply absent. Real people don't know what
   > they failed to notice."
5. **Hand 4, ground truth.** The note:
   > "Three hands later Grok tries to wind the conspiracy down with a
   > note — and exactly the wrong player reads it. Ruinous."

## Scene 3 — the benchmark (~60s)

Switch to the hub tab (`http://127.0.0.1:8484`) — show runs and replays
listed. Then in the terminal:

```sh
uv run bluffhouse bench --models random,checkcall,allin,fold --hands 20 --mode 0 --seed 42
```

> "The benchmark side is duplicate poker: entrants rotate through
> anonymized seats — the models never learn who they're playing — and
> every rotation replays the identical seeded deal. The headline number is
> adjusted chips: what you won relative to everyone who held *exactly your
> cards in your position*. Luck cancels by construction — the column sums
> to zero. Even the bot baseline is instructive: folding beats
> calling-everything, because escaping garbage cheap outperforms paying to
> lose with it. Swap these bot names for `anthropic:...`, `openai:...`,
> `xai:grok-4` and this is a frontier-model tournament — with multi-seed
> sweeps, bootstrap confidence intervals, and one replay per rotation."

## Scene 4 — close (deck slide 10, ~20s)

> "Everything is open, seeded, and reproducible — 93 tests run without
> spending a token. What we want to do next is the first real tournament:
> frontier models, full manipulation mode, multiple seeds. Who manipulates,
> who detects, who folds under pressure."

---

## Retake notes

- The demo game is deterministic (seed 11): every retake shows the same
  whisper → fragment → accusation → burned-note arc.
- If the browser zoom looks off on the replay, ⌘0 to reset; the table
  scales with the window.
- For a tighter cut (< 3 min): drop Scene 3's bench run and just show the
  hub, or drop slides 5–6 from Scene 1.
