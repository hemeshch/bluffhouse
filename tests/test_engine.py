"""HandEngine tests against fixed decks — exact, hand-verifiable poker."""

import pytest

from bluffhouse.engine import Deck, HandEngine
from bluffhouse.harness import EventLog
from bluffhouse.models import (
    ActionTaken,
    ActionType,
    BlindPosted,
    BoardDealt,
    HandEnded,
    HandStarted,
    HoleCardsDealt,
    PokerAction,
    PotAwarded,
    ShowdownReveal,
)

CALL = PokerAction(action=ActionType.CALL)
CHECK = PokerAction(action=ActionType.CHECK)
FOLD = PokerAction(action=ActionType.FOLD)


def raise_to(amount: int) -> PokerAction:
    return PokerAction(action=ActionType.RAISE_TO, amount=amount)


def make_engine(order, stacks, deck_prefix, sb=5, bb=10):
    log = EventLog()
    engine = HandEngine(
        hand_no=1,
        order=list(order),
        stacks=dict(stacks),
        small_blind=sb,
        big_blind=bb,
        deck=Deck.fixed(deck_prefix),
        emit=log.emit,
    )
    return engine, log


# hole cards dealt round-robin: A,B,C,D get (As Ah), (Kd Ks), (7c 7d), (2h 2s)
FOUR_HANDED_DECK = [
    "As", "Kd", "7c", "2h", "Ah", "Ks", "7d", "2s",
    "3c",              # burn
    "Qs", "Jh", "Ts",  # flop
    "4c", "9d",        # burn, turn
    "5c", "2c",        # burn, river
]


def events_of(log, cls):
    return [e for e in log.events if isinstance(e, cls)]


def test_scripted_hand_straight_beats_aces():
    engine, log = make_engine("ABCD", {a: 1000 for a in "ABCD"}, FOUR_HANDED_DECK)

    # deal order and privacy
    dealt = events_of(log, HoleCardsDealt)
    assert [(e.agent_id, e.cards) for e in dealt] == [
        ("A", ("As", "Ah")), ("B", ("Kd", "Ks")), ("C", ("7c", "7d")), ("D", ("2h", "2s")),
    ]
    assert all(e.visible_to == (e.agent_id,) for e in dealt)

    blinds = events_of(log, BlindPosted)
    assert [(e.agent_id, e.blind, e.amount) for e in blinds] == [("A", "small", 5), ("B", "big", 10)]

    # preflop: UTG (C) first; everyone calls, BB checks
    assert engine.actor == "C"
    assert engine.street == "preflop"
    for _ in range(3):
        engine.apply(CALL)
    engine.apply(CHECK)

    flop = events_of(log, BoardDealt)[0]
    assert flop.street == "flop" and flop.cards == ("Qs", "Jh", "Ts")

    # flop: A checks, B bets 30, C and D fold, A calls
    assert engine.actor == "A" and engine.street == "flop"
    engine.apply(CHECK)
    engine.apply(raise_to(30))
    engine.apply(FOLD)
    engine.apply(FOLD)
    engine.apply(CALL)

    # turn and river check down
    for _ in range(4):
        engine.apply(CHECK)

    assert engine.hand_over
    assert engine.board == ("Qs", "Jh", "Ts", "9d", "2c")
    # B's KdKs makes the straight and takes the 100 pot
    assert engine.stacks == {"A": 960, "B": 1060, "C": 990, "D": 990}
    awards = events_of(log, PotAwarded)
    assert [(e.agent_id, e.amount) for e in awards] == [("B", 100)]
    assert any(e.agent_id == "B" and e.cards == ("Kd", "Ks") for e in events_of(log, ShowdownReveal))

    ended = events_of(log, HandEnded)[0]
    assert ended.deltas == {"A": -40, "B": 60, "C": -10, "D": -10}
    assert sum(ended.stacks.values()) == 4000


def test_everyone_folds_uncalled_raise_returned():
    engine, log = make_engine("ABC", {a: 1000 for a in "ABC"}, [
        "As", "Kd", "7c", "Ah", "Ks", "7d",
    ])
    assert engine.actor == "C"
    engine.apply(raise_to(100))
    engine.apply(FOLD)  # A, small blind
    engine.apply(FOLD)  # B, big blind

    assert engine.hand_over
    # C collects the blinds plus its own uncalled raise back; net +15
    assert engine.stacks == {"A": 995, "B": 990, "C": 1015}
    assert [(e.agent_id, e.amount) for e in events_of(log, PotAwarded)] == [("C", 115)]
    assert events_of(log, HandEnded)[0].deltas == {"A": -5, "B": -10, "C": 15}
    assert events_of(log, ShowdownReveal) == []


def test_all_in_side_pots():
    engine, log = make_engine(
        "ABC",
        {"A": 100, "B": 300, "C": 1000},
        ["As", "Kd", "7c", "Ah", "Ks", "7d", "3c", "Qs", "Jh", "Ts", "4c", "9d", "5c", "2c"],
    )
    engine.apply(raise_to(1000))  # C shoves
    engine.apply(CALL)            # A all in for 100
    engine.apply(CALL)            # B all in for 300

    assert engine.hand_over
    # B's straight wins main pot (300) and side pot (400); C keeps its uncalled 700
    assert engine.stacks == {"A": 0, "B": 700, "C": 700}
    assert sum(e.amount for e in events_of(log, PotAwarded) if e.agent_id == "B") == 700
    assert len(events_of(log, ShowdownReveal)) == 3
    all_in_calls = [e for e in events_of(log, ActionTaken) if e.action is ActionType.CALL]
    assert all(e.all_in for e in all_in_calls)


def test_legal_actions_facing_raise():
    engine, _ = make_engine("ABCD", {a: 1000 for a in "ABCD"}, FOUR_HANDED_DECK)

    legal = engine.legal_actions()  # UTG facing the big blind
    assert legal.can_fold and legal.can_call and not legal.can_check
    assert legal.call_amount == 10
    assert legal.min_raise_to == 20 and legal.max_raise_to == 1000

    engine.apply(raise_to(30))
    legal = engine.legal_actions()  # D facing a raise to 30
    assert legal.call_amount == 30
    assert legal.min_raise_to == 50  # 30 plus the 20 raise increment

    engine.apply(FOLD)  # D
    engine.apply(FOLD)  # A
    engine.apply(FOLD)  # B
    assert engine.hand_over


def test_heads_up_button_is_small_blind_and_acts_first_preflop():
    engine, log = make_engine("AB", {"A": 1000, "B": 1000}, [
        "As", "Kd", "Ah", "Ks", "3c", "Qs", "Jh", "Ts",
    ])
    blinds = events_of(log, BlindPosted)
    assert {(e.agent_id, e.blind) for e in blinds} == {("A", "big"), ("B", "small")}
    assert engine.button == "B"
    assert engine.actor == "B"  # button/SB acts first preflop heads-up

    engine.apply(CALL)
    engine.apply(CHECK)
    assert engine.street == "flop"
    assert engine.actor == "A"  # big blind acts first postflop heads-up


def test_short_stack_posts_partial_blind():
    engine, log = make_engine("AB", {"A": 3, "B": 1000}, ["As", "Kd", "Ah", "Ks", "3c", "Qs", "Jh", "Ts", "4c", "9d", "5c", "2c"])
    blinds = events_of(log, BlindPosted)
    assert ("A", "big", 3) in {(e.agent_id, e.blind, e.amount) for e in blinds}  # all in from the blind
    # A is already all in; the hand should run out without anyone to act once B acts
    while not engine.hand_over:
        legal = engine.legal_actions()
        engine.apply(CHECK if legal.can_check else CALL)
    assert sum(engine.stacks.values()) == 1003


def test_event_stream_starts_with_hand_started():
    _, log = make_engine("ABCD", {a: 1000 for a in "ABCD"}, FOUR_HANDED_DECK)
    kinds = [type(e).__name__ for e in log.events[:7]]
    assert kinds == [
        "HandStarted", "BlindPosted", "BlindPosted",
        "HoleCardsDealt", "HoleCardsDealt", "HoleCardsDealt", "HoleCardsDealt",
    ]
    started = log.events[0]
    assert isinstance(started, HandStarted)
    assert started.button == "D" and started.seat_order == ("A", "B", "C", "D")
