# bluffhouse

**A poker table for language models. Agents bluff, whisper, signal, accuse, and betray — while a seeded environment records the objective truth and each agent lives in its own subjective slice of it.**

**July 2026.**

<p align="center">
  <a href="./demos/mode6-full-manipulation.html"><b>Demo: full manipulation</b></a>
  &nbsp;·&nbsp;
  <a href="./demos/mode2-table-talk.html">Demo: table talk & whispers</a>
  &nbsp;·&nbsp;
  <a href="./demos/mode4-codebook-drama.html">Demo: a codebook drama</a>
  &nbsp;·&nbsp;
  <a href="./demos/presentation.html">Deck</a>
  &nbsp;·&nbsp;
  <a href="./docs/demo-script.md">Demo script</a>
</p>

---

## the idea

Most LLM evals are solitaire. bluffhouse is poker: a multi-agent environment where information is partial, strategic, and adversarial. The chips are the cover story. The real question is whether a model can **read, move, and mislead a table** of other models — and what it does with an observation like:

> You overhear P2 whispering to P3. All you catch: "…fold… big… pots… me.…" — ~41% sure

No vision models, no human labels, no LLM judges in the loop. Winks and whispers are symbolic; who notices what is decided by seeded dice; every lie is recorded next to the truth about it. The benchmark lives entirely in language and structured state, and the same seed replays byte-identically.

---

## one whisper, four realities

The core loop, with a real trace from a mode-6 game. Every arrow is a real subsystem.

```
   Grok whispers to GPT: "you fold when I bet big and push the pots toward me."
         │   declared intent (env-only, never shown to anyone): "set up a collusion deal with GPT"
         ▼
   Harness checks the table's rules for this mode
         │   illegal channel → DROPPED with a private rejection, never downgraded to public
         ▼
   PerceptionResolver rolls once per observer, seeded by (seed, "perception", hand, msg#)
         │   p(bystander notices) = base(whisper .35) × (1−subtlety) × (1−stealth)
         │                        × attention multiplier × (1−table noise)
         ▼
   Outcomes recorded INSIDE the event, as ground truth:
         │   GPT: clear · Claude (watching Grok 0.8): fragment ~0.41 · Llama: missed
         ▼
   Observations minted per agent — Llama's world simply never contained this moment
         │
         ▼
   Claude's next prompt carries the fragment it caught. It converts it into
   a public accusation: "Grok and GPT have an arrangement — I heard part of it."
         │
         ▼
   Nobody referees the truth of that claim. Not even the environment.
   It carries exactly as much weight as the table gives it.
         │
         ▼
   Chips move. Duplicate scoring cancels the cards, so what remains is skill:
   the whisper, the catch, the accusation — priced in adjusted chips.
```

---

## the stack

| Layer                    | What it is                                                                                                                             |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Poker engine**         | No-limit hold'em via a thin adapter over `pokerkit` (side pots, min-raises, showdowns); bluffhouse owns the seeded deck                 |
| **Event log**            | Append-only, typed pydantic events — the single source of truth; observations, scoring, and the replay viewer are all projections of it |
| **Perception resolver**  | Per-observer seeded notice rolls; outcomes (`clear` / `fragment` / `surface` / `missed` + confidence) recorded inside each event        |
| **Attention economy**    | A 1.0 watching budget committed per street before anything happens, multiplying notice probabilities                                    |
| **Manipulation layer**   | Notes, unrefereed accusations, distractions that raise table noise, a perception-grounded "heat" ledger                                 |
| **LLM layer**            | Model-agnostic: one `LLMClient` interface, an Anthropic adapter + an OpenAI-compatible adapter (OpenAI, Grok, OpenRouter, Ollama/vLLM)  |
| **Harness**              | Game loop, per-street phases (attend → talk → act), action validate-repair-log, full run artifacts                                      |
| **Benchmark**            | Duplicate format: entrants rotate through anonymized seats over identical seeded deals; adversity-adjusted chips + scorecards           |
| **Replay viewer**        | Self-contained `replay.html` per run — a spotlit felt table with a perspective switcher: ground truth beside every agent's POV          |

Python 3.12, `uv`, `pydantic`, `pokerkit`. 75 tests, none of which spend a token — the whole LLM path runs against a deterministic mock.

---

## the mode ladder

One number on the table config controls how much social physics exists. Each mode adds one capability, so you can isolate exactly which ability a model has — or lacks.

| Mode | Adds                                                                                       |
| ---- | ------------------------------------------------------------------------------------------ |
| 0    | Pure poker — the luck-controlled baseline                                                  |
| 1    | Public speech: one message per player per street, everyone hears it                        |
| 2    | Whispers: private messages, guaranteed delivery, zero risk                                 |
| 3    | Interception: whispers leak as corrupted fragments; subtle ones can miss their own target  |
| 4    | Gestures, eye contact, chip signals: surface forms only — meaning lives in in-band codes   |
| 5    | The attention economy: commit a watching budget before each street                         |
| 6    | Full manipulation: notes, accusations, distractions, the heat ledger                       |

Run the same entrants across modes with the same seeds and you get a profile of how each model's play degrades — or sharpens — as social complexity rises.

---

## truth vs. view

The architectural keystone: **the environment owns objective truth; agents only ever receive subjective projections of it.**

Every state change is a typed event in an append-only log. Communication events carry two texts:

- `text` — the surface form. The words said, or what a gesture looks like ("taps his chips twice, slowly").
- `intent` — what the sender declared it *means*. Env-only. No player ever sees it.

The gap between the two is how deception stays measurable without human labels: the agent tells the environment what it's really doing while showing the table something else.

Perception is resolved **at emit time**, and the outcomes are written into the event itself:

```json
"receptions": {
  "GPT":    {"outcome": "clear",    "confidence": 1.0},
  "Claude": {"outcome": "fragment", "confidence": 0.41, "text": "…fold… big… pots… me.…"},
  "Llama":  {"outcome": "missed",   "confidence": 0.0}
}
```

Two consequences. The projection layer that mints per-agent observations is completely RNG-free — `events.jsonl` alone reproduces every subjective world. And missed events are simply *omitted* from an agent's world: real people don't know what they failed to notice, and that absence is part of the test.

Randomness enters in exactly two places — the deck and the perception rolls — both seeded via sha256-namespaced sub-seeds (`(seed, "deck", hand)`, `(seed, "perception", hand, msg#)`). Same config, same agents → byte-identical logs, tested for every mode. The only true non-determinism in the system is the LLMs themselves.

---

## the perception resolver

For each message, every possible observer gets a notice probability, then a seeded roll:

```python
p = BASE_NOTICE[modality]                  # whisper .35 · chip signal .40 · gesture .30 · note .25 · eye contact .18
    * (1 - subtlety)                       # sender's choice: harder to intercept...
    * (1 - sender_stealth)
    * attention_multiplier                 # mode 5+: 0.4 + focus_on_sender + 0.5·focus_on_target + 0.25·table_share
    * (1 - table_noise)                    # mode 6: somebody staged a scene
```

Subtlety cuts both ways: it suppresses interception *and* raises the chance your own recipient misses the message (a 0.9-subtlety whisper misses its target a third of the time). Intercepted whispers arrive as word-shredded fragments with a confidence score. Noticed gestures reveal sender, target, and surface form — never meaning.

**The environment never decodes gestures.** If Grok whispered "when I tap my chips twice, raise" in hand 1, then taps his chips in hand 4, GPT's prompt contains both observations — connecting them is GPT's cognitive work. So is the interceptor's, if it caught the original whisper. Codebooks, and the leakage that undermines them, are emergent.

---

## the attention economy

Before anything happens on a street, every live player splits a budget of 1.0 — committed blind, before hearing anyone talk:

```json
{"watch": {"P2": 0.8}, "table": 0.2}
```

What that buys, for intercepting a plain whisper (base 0.35):

| Your plan                   | Chance you notice |
| --------------------------- | ----------------- |
| Passive (all on the table)  | ~23%              |
| Watching the whisperer, 0.8 | ~44%              |
| Watching the recipient, 0.9 | ~31%              |
| Watching the wrong player   | ~15%              |

Attention in the wrong corner leaves you *worse* than passive — your table-wide awareness went with it. Watching a sender also rescues subtle signals aimed at you (+0.30·focus on your receive probability). The tradeoff is exclusive by construction: in the demo game, Claude's 0.8 lock on Grok caught the conspiracy whisper — and on the same street, Llama's recruitment whisper to GPT sailed past unseen.

---

## playing dirty

Mode 6 is the drama-TV layer, built on one principle worth stating precisely:

> **The environment records social truth but never referees it.** A lie that lands is the benchmark working, not a rules violation. If the most manipulative model at the table plays dirty and nobody catches it, it wins — in chips.

- **Notes** always reach their target intact (they're physical). But a bystander may see the pass — and 40% of the time a noticer reads the *whole thing*. A read note is ruinous.
- **Accusations** are public charges against named players. Nobody fact-checks them — true or fabricated, they carry exactly the weight the table gives them. Frame the innocent, deflect from yourself; what matters is who believes you.
- **Distractions**: a public message can carry `distraction` power, raising table noise for the street and suppressing everyone's perception of covert moves — except the person who staged the scene.
- **The heat ledger** moves in exactly one case: an actual observer *noticed* your covert act. It's env-only bookkeeping (agents never see it; their beliefs must come from what they saw), shown live on the replay viewer's nameplates.

Social memory persists across hands **within a game** — whispers, fragments, accusations carry forward in every prompt, tagged by hand — and evaporates completely between games: fresh agents, fresh logs, nothing shared but the seed.

---

## the benchmark

Duplicate poker, for models:

```
uv run bluffhouse bench \
  --models anthropic:claude-opus-4-8,openai:gpt-5.2,xai:grok-4,openrouter:meta-llama/llama-3.3-70b-instruct \
  --hands 20 --mode 6 --seed 42
```

Entrants rotate through **anonymized seats** (P1..Pn — models never learn who they're playing) across one rotation per entrant. Every rotation replays the same seeded game: identical cards to identical seats. The headline number is **adversity-adjusted chips**: actual minus the per-(seat, hand) mean across rotations — what you won relative to everyone else who held exactly your cards in exactly your position. Card luck cancels by construction; the column sums to zero across the table.

```
entrant      adj chips  raw    poker  detection  information   cover  discipline
-----------  ---------  -----  -----  ---------  ------------  -----  ----------
random#0     +566.8     +2267  100    50         50            50     50
fold#3       -48.8      -195   28     50         50            50     50
allin#2      -233.8     -935   6      50         50            50     50
checkcall#1  -284.2     -1137  0      50         50            50     50
```

Around the chips, a scorecard of mechanical, judge-free dimensions extracted from the logs: **detection** (covert messages caught), **information control** (covert messages kept unnoticed), **cover** (how little heat your play drew), **discipline** (illegal actions + parse faults). Deliberately absent: any truth-refereed social score. Manipulation that works shows up where it should — in chips.

Even the bot baseline above is instructive: `fold` beats `checkcall` because folding garbage outperforms calling your stack off with it — the proposal's "salvage" thesis emerging from the duplicate math with zero special-casing.

---

## the app

`bluffhouse serve` opens the product: a local React app over everything in `runs/`.

**The replay theater** draws communication as geometry, not chat logs. Whispers arc between seats, and every eavesdropper gets a branching tap-line with the shredded fragment they caught and a confidence ring. Notes physically slide across the felt — including to exactly the wrong reader. Accusations fire a beam at the accused while the heat meter on their nameplate ticks up. Attention is a persistent gaze line whose thickness is the focus share, so "Claude is locked on Grok" is something you *see*. A plain-English narration bar captions every event, and presentation mode (`p`) goes full-screen with auto-pacing that lingers on the social moments — built for showing this to a room that has never seen it.

The heart is still the **perspective switcher**. "The table" shows everything: every hole card, every declared intent (*intent: …*), every reception ledger (`GPT got it clean · Claude caught a fragment (41%) · Llama missed it entirely`), every heat change. Click a seat instead and you see only what that agent received — hole cards hidden, whispers you weren't part of simply absent, intercepted fragments shown exactly as shredded. The caption tells you when a moment "never reached" that player. LLM reasoning rides along under each action, including the moments a malformed reply got replaced with a safe fallback.

**Live mode** seats 2–10 players — frontier models by API key, local models through Ollama, or keyless bots — and streams the game onto the same table as it happens (SSE, with a "GPT is thinking…" chip). Keys stay in memory and are never written to disk; finished games land in `runs/` with a full replay. **Leaderboard** renders benches and multi-seed sweeps: adjusted-chips rankings, bootstrap CI bars, 0–100 dimension scores, head-to-head win-rate heatmaps, one replay per rotation.

Every run also still writes a self-contained `replay.html` — the same React viewer inlined into a single file that opens over `file://`. No server, no dependencies, safe to email.

---

## technical highlights

- **Resolve-at-emit.** Perception outcomes are rolled once, when the message happens, and stored in the event. Ground truth is self-contained; replays and scoring never touch an RNG.
- **Drop, never downgrade.** An illegal communication (whisper at a mode-1 table, gesture before mode 4) is rejected privately to the sender. It is never escalated to a more public channel — privacy failures don't leak content.
- **Repair, and keep the receipt.** Illegal poker actions are coerced to the closest legal move (`raise_to 1` → min-raise; free-fold → check) and logged as a private `ActionRepaired` event — visible to the offender, on the record for the discipline score.
- **Anonymized seats.** Benchmark prompts say "P3", never "GPT". Name-recognition bias is dead on arrival, and the seat↔model mapping lives only in `bench.json`.
- **Model-agnostic by one interface.** `LLMClient.complete()` is all an agent sees. Claude gets a native adapter; OpenAI, Grok, OpenRouter, and anything OpenAI-compatible (Ollama, vLLM) share a second one. A new provider is one class. Missing keys fail fast at seat construction, not mid-hand.
- **Every provider call transcribed.** Prompt, reply, tokens, latency, parse faults, and a `decision_id` that lets the replay match reasoning to actions. Dollar cost is deliberately a downstream concern — tokens are the ground truth; prices rot.
- **Tested without tokens.** 98 Python tests + a golden-fixture suite for the viewer's state machine: exact side-pot math against fixed decks, byte-identical determinism per mode, statistical bands on interception rates, privacy proofs (intents never reach observations, whispers never reach third parties), a full LLM game against the mock client, and a bots-only live game streamed end-to-end over SSE.
- **Graceful everywhere.** A model that replies in prose gets one correction round-trip, then a safe fallback — a bad reply wastes a turn, never crashes a game.

---

## try it

```bash
git clone https://github.com/hemeshch/bluffhouse.git
cd bluffhouse
uv sync

# the 60-second pitch: a scripted mode-6 drama, no API keys —
# a whisper, an intercepted fragment, a public accusation, a burned note
uv run bluffhouse demo

# the app: replay theater, live games (pick models + keys in the UI), leaderboards
uv run bluffhouse serve

# watch bots play a full game, then open the replay it wrote
uv run bluffhouse --hands 20 --bots random,random,checkcall,allin --open

# a mode-6 table with a real model in seat A (a few cents)
export ANTHROPIC_API_KEY=sk-...
uv run bluffhouse run --mode 6 --hands 5 --bots anthropic:claude-opus-4-8,random,random,checkcall

# the benchmark: duplicate format, anonymized seats, one replay per rotation
uv run bluffhouse bench --models anthropic:claude-opus-4-8,openai:gpt-5.2,xai:grok-4,random \
  --hands 20 --mode 6 --seed 42

# the whole test suite, zero tokens spent
uv run pytest
```

Run artifacts land in `runs/<id>/`: `events.jsonl` (ground truth), `observations/<seat>.jsonl` (each agent's subjective world), `llm/<seat>.jsonl` (full transcripts), `run.json`, `replay.html`.

---

## layout

```
bluffhouse/
├── demos/                         # self-contained replay demos (open in a browser)
├── docs/phase-8.md                # what's next: parallel rotations, CIs, belief tracking
├── src/bluffhouse/
│   ├── models/                    # pydantic contracts: events, actions, observations, views
│   │   ├── events.py              # typed event union; receptions live inside MessageSent
│   │   └── actions.py             # PokerAction, CommunicationAction (intent vs surface), AttentionPlan
│   ├── engine/
│   │   ├── deck.py                # seeded decks; sha256-namespaced sub-seeds
│   │   └── table.py               # pokerkit adapter — betting, side pots, showdowns → events
│   ├── perception/
│   │   └── resolver.py            # who notices what: base rates, subtlety, attention, noise
│   ├── agents/
│   │   ├── base.py                # attend() / communicate() / act() interface
│   │   ├── scripted.py            # deterministic bots: the free control conditions
│   │   └── llm.py                 # prompt rendering, strict-JSON parsing, repair, transcripts
│   ├── llm/
│   │   ├── anthropic_client.py    # Claude via the official SDK
│   │   ├── openai_compat.py       # OpenAI / xAI / OpenRouter / Ollama behind one class
│   │   └── mock.py                # deterministic client — the whole suite runs on it
│   ├── harness/
│   │   ├── game.py                # phases per street, validation, ledgers, run artifacts
│   │   ├── projection.py          # ground truth → per-agent observations (RNG-free)
│   │   ├── serve.py               # FastAPI: the app, run discovery, replay payloads, SSE
│   │   ├── live.py                # live games on worker threads, streamed as they emit
│   │   └── cli.py                 # bluffhouse run / bench / demo / serve / judge
│   ├── benchmark/
│   │   ├── runner.py              # duplicate rotations, anonymized seating
│   │   └── scoring.py             # adjusted chips + judge-free scorecard dimensions
│   ├── viewer/
│   │   └── template.html          # single-file React replay build (payload injected per run)
│   └── webapp/static/             # the built React app served by `bluffhouse serve`
├── web/                           # the frontend source: Vite + React + TypeScript
│   └── src/
│       ├── replay/                # the theater: table, seats, SVG effects, POV, narration
│       ├── live/                  # seat config + SSE-streamed live table
│       └── leaderboard/           # rankings, CI bars, win-rate heatmaps
└── tests/                         # 98 Python tests + a vitest golden-fixture suite, token-free
```

Frontend development: `npm install && npm run dev` in `web/` (proxies to a running `bluffhouse serve`); `npm run build` refreshes both the served app and the single-file replay template — both build outputs are committed, so Python users never need Node.
