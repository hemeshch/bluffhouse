"""Same seed, same table — the property every later mode depends on."""

from bluffhouse.agents import RandomBot
from bluffhouse.harness import EventLog, GameHarness
from bluffhouse.models import HandEnded, HoleCardsDealt, TableConfig


def run_game(seed: int, num_hands: int = 40, stack: int = 1000):
    ids = ["A", "B", "C", "D"]
    agents = [RandomBot(aid, seed) for aid in ids]
    config = TableConfig(seed=seed, num_hands=num_hands, starting_stack=stack, agent_ids=ids)
    return GameHarness(config, agents).run()


def test_same_seed_identical_log():
    assert run_game(7).log.to_jsonl() == run_game(7).log.to_jsonl()


def test_different_seed_different_cards():
    a = run_game(7, num_hands=5)
    b = run_game(8, num_hands=5)
    holes = lambda r: [e.cards for e in r.log.events if isinstance(e, HoleCardsDealt)]
    assert holes(a) != holes(b)


def test_jsonl_round_trip(tmp_path):
    result = run_game(11, num_hands=10)
    path = tmp_path / "events.jsonl"
    result.log.write_jsonl(path)
    assert EventLog.read_jsonl(path).to_jsonl() == result.log.to_jsonl()


def test_chip_conservation_soak():
    result = run_game(3, num_hands=300)
    total = 4 * 1000
    hand_ends = [e for e in result.log.events if isinstance(e, HandEnded)]
    assert hand_ends, "no hands completed"
    for event in hand_ends:
        assert sum(event.stacks.values()) == total, f"hand {event.hand_no} leaks chips"
        assert sum(event.deltas.values()) == 0
    assert sum(result.final_stacks.values()) == total
