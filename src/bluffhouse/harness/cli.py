"""Command-line entry point: play a mode-0 table and write the run
artifacts (ground-truth events, per-agent observations, LLM transcripts).

Seats take scripted bots or LLM players from any provider:
    --bots anthropic:claude-opus-4-8,openai:gpt-5.2,xai:grok-4,random
"""

import argparse
from datetime import datetime
from pathlib import Path

from bluffhouse.agents import Agent, AllInBot, CheckCallBot, FoldBot, LLMAgent, RandomBot
from bluffhouse.harness.game import GameHarness, GameResult
from bluffhouse.llm import AnthropicClient, LLMError, OpenAICompatClient
from bluffhouse.models import BoardDealt, HandEnded, HandStarted, PotAwarded, ShowdownReveal, TableConfig

BOT_KINDS = ("random", "checkcall", "fold", "allin")
LLM_PROVIDERS = ("anthropic", "claude", "openai", "xai", "grok", "openrouter", "ollama")


def build_agent(kind: str, agent_id: str, seed: int) -> Agent:
    if kind == "random":
        return RandomBot(agent_id, seed)
    if kind == "checkcall":
        return CheckCallBot(agent_id)
    if kind == "fold":
        return FoldBot(agent_id)
    if kind == "allin":
        return AllInBot(agent_id)

    provider, _, model = kind.partition(":")
    provider = provider.lower()
    try:
        if provider in ("anthropic", "claude"):
            return LLMAgent(agent_id, AnthropicClient(model or "claude-opus-4-8"))
        if provider in ("openai", "xai", "grok", "openrouter", "ollama"):
            if not model:
                raise SystemExit(f"'{provider}' seats need a model, e.g. {provider}:MODEL")
            preset = {"grok": "xai"}.get(provider, provider)
            return LLMAgent(agent_id, OpenAICompatClient(model, preset=preset))
    except LLMError as exc:
        raise SystemExit(f"seat {agent_id} ({kind}): {exc}") from exc
    raise SystemExit(
        f"unknown seat '{kind}' — use a bot ({'|'.join(BOT_KINDS)}) "
        f"or provider:model ({'|'.join(LLM_PROVIDERS)})"
    )


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
    from bluffhouse.benchmark import run_benchmark

    parser = argparse.ArgumentParser(
        prog="bluffhouse bench",
        description="Duplicate-format benchmark: entrants rotate through "
        "anonymized seats over identical seeded games.",
    )
    parser.add_argument(
        "--models", required=True,
        help="comma-separated entrants (same specs as --bots): "
        "anthropic:MODEL, openai:MODEL, openrouter:V/M, random, checkcall, ...",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hands", type=int, default=20)
    parser.add_argument("--mode", type=int, default=6)
    parser.add_argument("--rotations", type=int, default=None,
                        help="default: one per entrant (everyone sits everywhere)")
    parser.add_argument("--stack", type=int, default=1000)
    parser.add_argument("--sb", type=int, default=5)
    parser.add_argument("--bb", type=int, default=10)
    parser.add_argument("--out", default="runs/bench")
    args = parser.parse_args(argv)
    if args.mode > 6:
        raise SystemExit(f"modes run 0–6; {args.mode} does not exist")

    specs = [s.strip() for s in args.models.split(",") if s.strip()]
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
    )
    print(result.table())
    out = result.write(Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}-seed{args.seed}")
    print(f"\nbenchmark written to {out}/ (bench.json + one replay per rotation)")


def main(argv: list[str] | None = None) -> None:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "bench":
        return bench_main(argv[1:])
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


if __name__ == "__main__":
    main()
