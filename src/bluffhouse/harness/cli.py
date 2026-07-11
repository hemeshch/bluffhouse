"""Command-line entry point: play a mode-0 table and write the run
artifacts (ground-truth events, per-agent observations, LLM transcripts).

Seats take scripted bots or LLM players from any provider:
    --bots anthropic:claude-opus-4-8,openai:gpt-5.2,xai:grok-4,random
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from bluffhouse.agents import Agent, AllInBot, CheckCallBot, FoldBot, LLMAgent, RandomBot
from bluffhouse.harness.game import GameHarness, GameResult
from bluffhouse.llm import AnthropicClient, LLMClient, LLMError, OpenAICompatClient
from bluffhouse.models import BoardDealt, HandEnded, HandStarted, PotAwarded, ShowdownReveal, TableConfig

BOT_KINDS = ("random", "checkcall", "fold", "allin")
LLM_PROVIDERS = ("anthropic", "claude", "openai", "xai", "grok", "openrouter", "ollama")


def build_client(kind: str) -> LLMClient:
    provider, _, model = kind.partition(":")
    provider = provider.lower()
    try:
        if provider in ("anthropic", "claude"):
            return AnthropicClient(model or "claude-opus-4-8")
        if provider in ("openai", "xai", "grok", "openrouter", "ollama"):
            if not model:
                raise SystemExit(f"'{provider}' needs a model, e.g. {provider}:MODEL")
            preset = {"grok": "xai"}.get(provider, provider)
            return OpenAICompatClient(model, preset=preset)
    except LLMError as exc:
        raise SystemExit(f"model {kind}: {exc}") from exc
    raise SystemExit(
        f"unknown model '{kind}' — use provider:model ({'|'.join(LLM_PROVIDERS)})"
    )


def build_agent(kind: str, agent_id: str, seed: int) -> Agent:
    if kind == "random":
        return RandomBot(agent_id, seed)
    if kind == "checkcall":
        return CheckCallBot(agent_id)
    if kind == "fold":
        return FoldBot(agent_id)
    if kind == "allin":
        return AllInBot(agent_id)
    return LLMAgent(agent_id, build_client(kind))


def print_summary(result: GameResult) -> None:
    board: tuple[str, ...] = ()
    winners: list[str] = []
    shows: dict[str, str] = {}
    for event in result.log.events:
        if isinstance(event, HandStarted):
            board, winners, shows = (), [], {}
        elif isinstance(event, BoardDealt):
            board = event.board
        elif isinstance(event, ShowdownReveal):
            shows[event.agent_id] = f"{event.cards[0]} {event.cards[1]}"
        elif isinstance(event, PotAwarded):
            shown = f" ({shows[event.agent_id]})" if event.agent_id in shows else ""
            winners.append(f"{event.agent_id} +{event.amount}{shown}")
        elif isinstance(event, HandEnded):
            board_str = " ".join(board) if board else "no flop"
            print(f"hand {event.hand_no:>3} | {board_str:<14} | {', '.join(winners)}")

    print(f"\nfinal stacks after {result.hands_played} hands:")
    for aid, stack in sorted(result.final_stacks.items(), key=lambda kv: -kv[1]):
        delta = stack - result.config.starting_stack
        print(f"  {aid}: {stack}  ({delta:+d})")


def bench_main(argv: list[str]) -> None:
    from bluffhouse.benchmark import run_benchmark, run_benchmark_sweep
    from bluffhouse.harness.game import GameResult

    parser = argparse.ArgumentParser(
        prog="bluffhouse bench",
        description="Duplicate-format benchmark: entrants rotate through "
        "anonymized seats over identical seeded games.",
    )
    parser.add_argument(
        "--models",
        help="comma-separated entrants (same specs as --bots): "
        "anthropic:MODEL, openai:MODEL, openrouter:V/M, random, checkcall, ...",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seeds", default=None, help="comma-separated seeds for a sweep")
    parser.add_argument(
        "--num-seeds",
        type=int,
        default=None,
        help="run K seeds starting at --seed",
    )
    parser.add_argument("--hands", type=int, default=20)
    parser.add_argument("--mode", type=int, default=6)
    parser.add_argument("--rotations", type=int, default=None,
                        help="default: one per entrant (everyone sits everywhere)")
    parser.add_argument("--stack", type=int, default=1000)
    parser.add_argument("--sb", type=int, default=5)
    parser.add_argument("--bb", type=int, default=10)
    parser.add_argument(
        "--parallel",
        type=int,
        default=None,
        help="rotation workers; default: one worker per missing rotation",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="existing benchmark directory; completed rotation-* dirs are reused",
    )
    parser.add_argument(
        "--no-beliefs", action="store_true",
        help="skip per-street belief reports (saves one LLM call per agent per street)",
    )
    parser.add_argument("--out", default="runs/bench")
    args = parser.parse_args(argv)
    if args.mode > 6:
        raise SystemExit(f"modes run 0–6; {args.mode} does not exist")

    def specs_from_entrants(entrants: list[str]) -> list[str]:
        return [entrant.rpartition("#")[0] or entrant for entrant in entrants]

    seeds: list[int] | None = None
    if args.resume:
        bench_dir = Path(args.resume)
        bench_json = bench_dir / "bench.json"
        leaderboard_json = bench_dir / "leaderboard.json"
        if bench_json.exists():
            previous = json.loads(bench_json.read_text(encoding="utf-8"))
            specs = specs_from_entrants(previous["entrants"])
            args.seed = previous["seed"]
            args.hands = previous["num_hands"]
            args.mode = previous["mode"]
            args.rotations = len(previous["seatings"])
        elif leaderboard_json.exists():
            previous = json.loads(leaderboard_json.read_text(encoding="utf-8"))
            specs = specs_from_entrants(previous["entrants"])
            seeds = [int(seed) for seed in previous["seeds"]]
            args.hands = previous["num_hands"]
            args.mode = previous["mode"]
            args.rotations = previous.get("rotations")
        elif args.models:
            specs = [s.strip() for s in args.models.split(",") if s.strip()]
        else:
            raise SystemExit(
                "--resume needs bench.json, leaderboard.json, or a fresh --models list"
            )

        existing = sorted(bench_dir.glob("rotation-*/run.json"))
        existing += sorted(bench_dir.glob("seed-*/rotation-*/run.json"))
        if existing:
            cfg = GameResult.read(existing[0].parent).config
            args.stack = cfg.starting_stack
            args.sb = cfg.small_blind
            args.bb = cfg.big_blind
    else:
        if not args.models:
            raise SystemExit("--models is required unless --resume points at a bench")
        specs = [s.strip() for s in args.models.split(",") if s.strip()]
        suffix = "seeds" if (args.seeds or args.num_seeds) else f"seed{args.seed}"
        bench_dir = Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}-{suffix}"

    if args.seeds:
        seeds = [int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    elif args.num_seeds is not None:
        if args.num_seeds < 1:
            raise SystemExit("--num-seeds must be at least 1")
        seeds = list(range(args.seed, args.seed + args.num_seeds))

    if seeds is not None:
        result = run_benchmark_sweep(
            specs,
            builder=build_agent,
            seeds=seeds,
            num_hands=args.hands,
            mode=args.mode,
            rotations=args.rotations,
            small_blind=args.sb,
            big_blind=args.bb,
            starting_stack=args.stack,
            collect_beliefs=not args.no_beliefs,
            parallel=args.parallel,
            out_dir=bench_dir,
            resume_dir=bench_dir if args.resume else None,
        )
        print(result.table())
        print(
            f"\nbenchmark sweep written to {bench_dir}/ "
            "(leaderboard.json + per-seed benches)"
        )
        return

    result = run_benchmark(
        specs,
        builder=build_agent,
        seed=args.seed,
        num_hands=args.hands,
        mode=args.mode,
        rotations=args.rotations,
        small_blind=args.sb,
        big_blind=args.bb,
        starting_stack=args.stack,
        collect_beliefs=not args.no_beliefs,
        parallel=args.parallel,
        out_dir=bench_dir,
        resume_dir=bench_dir if args.resume else None,
    )
    print(result.table())
    print(f"\nbenchmark written to {bench_dir}/ (bench.json + one replay per rotation)")


def judge_main(argv: list[str]) -> None:
    from bluffhouse.benchmark import judge_run

    parser = argparse.ArgumentParser(
        prog="bluffhouse judge",
        description="Offline LLM-judge pass over one completed run directory.",
    )
    parser.add_argument("run_dir")
    parser.add_argument("--model", required=True, help="provider:model judge model")
    args = parser.parse_args(argv)

    judgments = judge_run(args.run_dir, build_client(args.model))
    print(f"judged {len(judgments)} messages; wrote {Path(args.run_dir) / 'judgments.jsonl'}")


def demo_main(argv: list[str]) -> None:
    import webbrowser

    from bluffhouse.demo import DEMO_SEED, demo_game

    parser = argparse.ArgumentParser(
        prog="bluffhouse demo",
        description="Play the scripted mode-6 showcase (no API keys) and open the replay.",
    )
    parser.add_argument("--seed", type=int, default=DEMO_SEED)
    parser.add_argument("--out", default="runs")
    parser.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = parser.parse_args(argv)

    result = demo_game(args.seed)
    run_dir = result.write(
        Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}-demo-seed{args.seed}"
    )
    print("demo game complete — a whisper, an intercepted fragment, a public")
    print("accusation, a covered note, and a note read by the wrong player.")
    print(f"replay: {run_dir / 'replay.html'}")
    if not args.no_open:
        webbrowser.open((run_dir / "replay.html").resolve().as_uri())


def serve_main(argv: list[str]) -> None:
    from bluffhouse.harness.serve import serve

    parser = argparse.ArgumentParser(
        prog="bluffhouse serve",
        description="Local hub over the runs directory: browse games, benches, "
        "and leaderboards; click through to replays.",
    )
    parser.add_argument("--dir", default="runs")
    parser.add_argument("--port", type=int, default=8484)
    parser.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = parser.parse_args(argv)
    serve(args.dir, port=args.port, open_browser=not args.no_open)


def main(argv: list[str] | None = None) -> None:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "bench":
        return bench_main(argv[1:])
    if argv and argv[0] == "judge":
        return judge_main(argv[1:])
    if argv and argv[0] == "demo":
        return demo_main(argv[1:])
    if argv and argv[0] == "serve":
        return serve_main(argv[1:])
    if argv and argv[0] == "run":
        argv = argv[1:]
    return run_main(argv)


def run_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="bluffhouse",
        description="bluffhouse harness — play one table (add `bench` for benchmarks).",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hands", type=int, default=20)
    parser.add_argument(
        "--bots",
        default="random,random,random,random",
        help=f"comma-separated seats: bot kind ({'|'.join(BOT_KINDS)}) "
        "or provider:model (anthropic:claude-opus-4-8, openai:MODEL, xai:MODEL, "
        "openrouter:VENDOR/MODEL, ollama:MODEL)",
    )
    parser.add_argument("--stack", type=int, default=1000)
    parser.add_argument("--sb", type=int, default=5)
    parser.add_argument("--bb", type=int, default=10)
    parser.add_argument(
        "--mode", type=int, default=0,
        help="0 = pure poker, 1 = public table talk, 2 = + private messages, "
        "3 = + interception, 4 = + gestures, 5 = + attention economy, "
        "6 = full manipulation (notes, accusations, distractions, ledgers)",
    )
    parser.add_argument("--out", default="runs", help="directory for run artifacts")
    parser.add_argument("--quiet", action="store_true", help="skip the hand-by-hand summary")
    parser.add_argument(
        "--no-beliefs", action="store_true",
        help="skip per-street belief reports (saves one LLM call per agent per street)",
    )
    parser.add_argument("--open", action="store_true", help="open the replay when done")
    args = parser.parse_args(argv)
    if args.mode > 6:
        raise SystemExit(f"modes run 0–6; {args.mode} does not exist")

    kinds = [k.strip() for k in args.bots.split(",") if k.strip()]
    ids = [chr(ord("A") + i) for i in range(len(kinds))]
    agents = [build_agent(kind, aid, args.seed) for kind, aid in zip(kinds, ids)]
    config = TableConfig(
        seed=args.seed,
        num_hands=args.hands,
        small_blind=args.sb,
        big_blind=args.bb,
        starting_stack=args.stack,
        agent_ids=ids,
        mode=args.mode,
        collect_beliefs=not args.no_beliefs,
    )

    result = GameHarness(config, agents).run()
    if not args.quiet:
        print_summary(result)

    run_dir = Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}-seed{args.seed}"
    result.write(run_dir)

    llm_agents = [a for a in agents if isinstance(a, LLMAgent)]
    if llm_agents:
        print("\nllm usage:")
        for agent in llm_agents:
            calls = len(agent.transcript)
            faults = sum(1 for c in agent.transcript if c.parse_error)
            tokens_in, tokens_out = agent.token_totals
            print(
                f"  {agent.id} ({agent.client.model}): {calls} calls, "
                f"{faults} faults, {tokens_in:,} in / {tokens_out:,} out tokens"
            )

    print(f"\nrun artifacts written to {run_dir}/")
    if args.open:
        import webbrowser

        webbrowser.open((run_dir / "replay.html").resolve().as_uri())


if __name__ == "__main__":
    main()
