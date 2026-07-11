# Demo recording script (~5 minutes)

A scene-by-scene guide for recording the bluffhouse demo video. Everything
runs locally, needs **no API keys**, and is deterministic — you can retake
any scene and get the identical game.

## Setup (before recording)

```sh
cd bluffhouse
uv sync && uv run pytest -q        # confidence check: 98 passed
open demos/presentation.html        # the deck, full-screen it (⌃⌘F in most browsers)
uv run bluffhouse serve             # the app on http://127.0.0.1:8484
# in the app: click "Watch the demo game" once, so the run exists
# optional, for the leaderboard scene:
uv run bluffhouse bench --models random,checkcall,allin,fold --hands 20 --mode 0 --seed 42
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

Switch to the app (`http://127.0.0.1:8484`), click **Watch the demo game**,
then press **p** — presentation mode. Now the money sequence:

1. **Ground truth first.** Hand 1, press space (or → to step). Pause on the
   whisper:
   > "Watch the table, not a chat log. That violet arc is Grok whispering a
   > collusion deal to GPT — and that thinner branching line is Claude
   > *intercepting* it. The narration shows the words and the private
   > intent — 'set up a collusion deal with GPT' — and the reception
   > ledger: GPT got it clean, **Claude caught a fragment at 41%
   > confidence**, Llama missed it entirely."
2. **Press p to exit presentation, switch POV → Claude.** Step back over
   the same moment:
   > "Here's the same moment from Claude's chair: just a shredded
   > fragment — '…fold… big… pots… me.…'. Notice the gaze line — Claude
   > was spending 60% of its attention watching Grok. That's the attention
   > economy paying off."
3. **The accusation.** Step to the flop:
   > "Claude converts that fragment into a public accusation — the red
   > beam. Nobody fact-checks it — it lands only as hard as the table
   > believes it. Watch the heat bar under Grok's nameplate tick up."
4. **Switch POV → Llama**, scrub back to hand 1:
   > "And from Llama's seat? The whisper never existed. Missed events
   > aren't marked — they're simply absent. Real people don't know what
   > they failed to notice."
5. **Hand 4, ground truth.** The note:
   > "Three hands later Grok tries to wind the conspiracy down with a
   > note — watch it slide across the felt — and exactly the wrong player
   > reads it. Ruinous."

## Scene 3 — live mode + the benchmark (~90s)

Click **Play live** in the top nav:

> "This is the same harness pointed at real models: pick a provider per
> seat, paste a key — keys live in memory, never on disk — or seat scripted
> bots for free. Everything streams as it happens."

Click **Bots scrimmage (no keys)** → **Deal the game** — a full game plays
out live in seconds. Then click **Leaderboard**:

> "The benchmark side is duplicate poker: entrants rotate through
> anonymized seats — the models never learn who they're playing — and
> every rotation replays the identical seeded deal. The headline number is
> adjusted chips: what you won relative to everyone who held *exactly your
> cards in your position*. Luck cancels by construction — the column sums
> to zero. Even the bot baseline is instructive: folding beats
> calling-everything, because escaping garbage cheap outperforms paying to
> lose with it. Swap these bot names for `anthropic:...`, `openai:...`,
> `xai:grok-4` and this is a frontier-model tournament — with multi-seed
> sweeps, bootstrap confidence intervals, win-rate matrices, and one
> replay per rotation."

## Scene 4 — close (deck slide 10, ~20s)

> "Everything is open, seeded, and reproducible — 98 tests run without
> spending a token, and every run writes a single-file replay you can
> email. What we want to do next is the first real tournament: frontier
> models, full manipulation mode, multiple seeds. Who manipulates, who
> detects, who folds under pressure."

---

## Retake notes

- The demo game is deterministic (seed 11): every retake shows the same
  whisper → fragment → accusation → burned-note arc.
- Deep links jump straight to a moment, e.g.
  `/#/replay?dir=demo-seed11&hand=1&at=11` (the whisper) — add `&pov=Claude`
  for the fragment view, `&present=1` for presentation mode.
- Keyboard in the replay: ←/→ step, space plays, **p** presentation, **?**
  shows the audience legend.
- For a tighter cut (< 3 min): drop the live-mode beat from Scene 3 and
  just show the leaderboard, or drop slides 5–6 from Scene 1.
