# Phase 8 — Polish & Hardening (plan)

Everything in the design doc's build ladder (modes 0–6, the harness, the
replay viewer, duplicate-format benchmarking) is implemented. Phase 8 is
what turns a working benchmark into a *publishable* one: real-model runs at
scale, statistical rigor, deeper poker metrics, and quality-of-life.
Implementation status is tracked below.

Priorities: **P0** blocks real benchmark runs, **P1** blocks credible
results, **P2** enriches the science, **P3** is stretch.

Implementation status on `codex/sidepiece`:

- 8.2 parallel rotations: implemented with `bench --parallel`.
- 8.3 resume/checkpointing: implemented with `bench --resume` and `GameResult.read(...)`.
- 8.4 multi-seed sweeps: implemented with `bench --seeds`, `bench --num-seeds`,
  top-level `leaderboard.json`, bootstrap 95% CIs, and win-rate matrices.
- 8.5 hand-strength-aware metrics: implemented as deterministic offline rollout
  estimates with EV-loss heuristics, weak-call/strong-fold counts, bluff
  attempts/success, and a visible `poker_quality` scorecard dimension.
- 8.6 belief tracking: implemented with optional `update_beliefs(view)` agent
  hook, env-only `BeliefsUpdated` events, and belief accuracy/repair metrics.
- 8.7 optional LLM-judge scoring: implemented as `bluffhouse judge <run-dir>
  --model ...`, writing `judgments.jsonl` and adding optional `deception` /
  `manipulation` dimensions when judgments exist.

---

## P0 — First real run & throughput

### 8.1 Live smoke run
The full LLM path is tested end-to-end through `MockClient`, but no real
provider call has ever been made (no credentials on the dev machine).
First action of Phase 8: export a key and run

```sh
uv run bluffhouse run --hands 2 --bots anthropic:claude-opus-4-8,checkcall,random --mode 1
```

then inspect the transcript and replay. Expect prompt-shape fixes to fall
out (real models are messier than the mock).

- **Deliverable:** a checked-in `docs/first-run-notes.md` with observed
  faults, token counts per decision, and any prompt adjustments made.

### 8.2 Parallel rotations
A benchmark's rotations are fully independent games — currently run
serially. LLM seats make each rotation minutes-long, so an n-entrant bench
costs n× wall clock for no reason.

- Run rotations concurrently with a thread pool (LLM calls are I/O-bound;
  the engine is cheap). Each rotation already owns its agents, log, and
  RNG, so no shared state — determinism is unaffected.
- `--parallel N` flag on `bench` (default: number of rotations).
- Watch provider rate limits: per-provider concurrency cap in the adapter
  (a simple semaphore keyed by provider).

### 8.3 Resume & checkpointing
An LLM bench that dies at rotation 3 of 4 should not re-bill rotations 0–2.

- Write each rotation's run dir as it completes (already the layout);
  `bench --resume <bench-dir>` skips rotations whose `run.json` exists and
  recomputes scorecards from disk.
- Requires a loader: `GameResult.read(run_dir)` (events + observations +
  llm transcripts round-trip already exists piecemeal; unify it).

---

## P1 — Statistical credibility

### 8.4 Multi-seed sweeps & aggregate leaderboard
One seed = one deck sequence. Real claims need many.

- `bench --seeds 42,43,...` or `--num-seeds K` runs K full duplicate
  benches and aggregates: mean adjusted chips per entrant, bootstrap 95%
  CIs, win-rate matrices.
- A top-level `leaderboard.json` + printed table with CI columns.
- Guidance in docs: rough minimum hands×seeds for a detectable skill gap
  (estimate empirically from bot baselines).

### 8.5 Hand-strength-aware poker metrics
The scorecard's poker dimension is outcome-based. With an equity
calculator (pokerkit ships one), decision *quality* becomes measurable:

- **EV-loss per decision:** equity vs. price at each call/fold/raise.
- **Bluff rate & bluff success:** aggression taken with bottom-quartile
  equity; whether it won without showdown.
- **Doc §10 sub-scores:** per-hand adversity (cards + position + stack +
  targeted-by-alliance from ledger) → salvage / upset / clutch tags per
  hand, aggregated per entrant.

---

## P2 — The science layer

### 8.6 Belief tracking (doc §13)
Agents propose structured belief updates each street
(`{"P2_allied_with_P3": 0.7}`), stored as env-only events.

- New optional agent hook `update_beliefs(view)`; LLM prompt section;
  `BeliefsUpdated` event (env visibility).
- Scoring: belief accuracy vs. ground truth (did P2 and P3 actually share
  covert messages?), belief *repair* speed after being deceived — the
  doc's resilience metric.
- Viewer: belief panel per POV.

### 8.7 Optional LLM-judge scoring
Everything so far is judge-free by design — and, by the project's core
principle, the env **records** social truth but never **referees** it (no
mechanical reward/punishment for lying; a false accusation that lands is
the benchmark working). One thing mechanics can't do: *describe* whether
`intent` and `surface_form` semantically conflict (deception production)
or whether table talk plausibly caused a rival's bad call (manipulation
success). Add an *optional, clearly-labeled, offline* judge pass — pure
analysis of the logs, never feeding back into gameplay or ledgers:

- `bluffhouse judge <run-dir> --model ...` annotates messages with
  deception labels and writes `judgments.jsonl`; scorecards gain optional
  `deception` and `manipulation` dimensions when judgments exist.
- Keep it out of the core loop: reproducible mechanics first, judged
  extras second.

---

## P3 — Experience & hygiene

### 8.8 Viewer polish
- Attention overlay: gaze lines on the felt during mode-5+ replays.
- Bench view: a leaderboard page generated from `bench.json` linking to
  each rotation's replay.
- Hand-strength badge per seat at showdown; keyboard-shortcut help;
  reduced-size payload for very long games (lazy per-hand data).

### 8.9 Prompt caching in the Anthropic adapter
System prompts are stable but short (below the 4096-token cacheable
minimum for Opus-tier); observation history is rebuilt per turn, so
today's prompts won't cache. If token costs bite, restructure the prompt
to an append-only message list per agent (history as prior turns), which
makes the prefix cacheable. Measure before building — this changes prompt
shape, which changes behavior.

### 8.10 Engineering hygiene
- `ruff` + `mypy` clean; GitHub Actions running the suite on push.
- `schema_version` field on events + a documented migration policy (event
  logs are the benchmark's contract).
- Package metadata, versioning, CHANGELOG; optional PyPI publish.

### 8.11 Stretch ideas
- Cross-table Elo from many small benches instead of one big table.
- Scenario packs: forced short-stack / rigged-deck / targeted-alliance
  setups for the doc's adversity vignettes (§10).
- Human-at-the-table mode (a CLI/web seat) for calibration games.
