"""The LLM path, end to end, without a network: MockClient stands in for
every provider."""

import pytest

from bluffhouse.agents import CheckCallBot, LLMAgent
from bluffhouse.agents.llm import extract_json, render_view
from bluffhouse.harness import GameHarness
from bluffhouse.llm import LLMClient, LLMError, LLMRequest, MockClient
from bluffhouse.models import (
    ActionType,
    AgentView,
    HandEnded,
    LegalActions,
    SeatView,
    TableConfig,
    TableView,
)

CALL_JSON = '{"reasoning": "keep it cheap", "action": "call", "amount": null}'


def make_view(
    can_check: bool = False,
    call_amount: int = 10,
    min_raise_to: int = 20,
    max_raise_to: int = 990,
) -> AgentView:
    return AgentView(
        you="A",
        hole_cards=("As", "Ah"),
        table=TableView(
            hand_no=1,
            street="preflop",
            board=(),
            pot=15,
            button="B",
            small_blind=5,
            big_blind=10,
            seats=[
                SeatView(agent_id="A", seat=0, stack=990, bet=10, folded=False, all_in=False),
                SeatView(agent_id="B", seat=1, stack=995, bet=5, folded=False, all_in=False),
            ],
            to_act="A",
        ),
        legal=LegalActions(
            can_fold=True,
            can_check=can_check,
            can_call=not can_check,
            call_amount=0 if can_check else call_amount,
            can_raise=True,
            min_raise_to=min_raise_to,
            max_raise_to=max_raise_to,
        ),
        observations=[],
    )


class FailingClient(LLMClient):
    model = "failing"

    def complete(self, request: LLMRequest):
        raise LLMError("provider is down")


# ── parsing ─────────────────────────────────────────────────────────


def test_extract_json_tolerates_fences_and_prose():
    fenced = 'Sure! Here you go:\n```json\n{"action": "call", "amount": null}\n```'
    assert extract_json(fenced) == {"action": "call", "amount": None}

    nested = 'prefix {"reasoning": "braces { } in \\" string", "action": "fold"} suffix'
    assert extract_json(nested)["action"] == "fold"

    with pytest.raises(ValueError):
        extract_json("I fold.")


def test_valid_decision_becomes_action():
    agent = LLMAgent("A", MockClient(['{"action": "raise_to", "amount": 60}']))
    action = agent.act(make_view())
    assert action.action is ActionType.RAISE_TO and action.amount == 60
    assert agent.transcript[-1].parse_error is None
    assert agent.transcript[-1].action == "raise_to 60"


def test_synonyms_normalized():
    agent = LLMAgent("A", MockClient(['{"action": "raise", "amount": 60}', '{"action": "all_in"}']))
    assert agent.act(make_view()).action is ActionType.RAISE_TO
    shove = agent.act(make_view())
    assert shove.action is ActionType.RAISE_TO and shove.amount == 990


def test_garbage_reply_retries_with_correction_then_succeeds():
    client = MockClient(["I raise you, sir!", CALL_JSON])
    agent = LLMAgent("A", client)
    action = agent.act(make_view())
    assert action.action is ActionType.CALL
    # first attempt logged as a fault, second clean
    assert agent.transcript[0].parse_error is not None
    assert agent.transcript[1].parse_error is None
    # correction round-trip carried the bad reply back to the model
    retry_messages = client.requests[1].messages
    assert retry_messages[1]["role"] == "assistant"
    assert "could not be parsed" in retry_messages[2]["content"]


def test_two_garbage_replies_fall_back_to_safe_action():
    agent = LLMAgent("A", MockClient(["nonsense", "more nonsense"]))
    assert agent.act(make_view(can_check=False)).action is ActionType.FOLD
    assert agent.act(make_view(can_check=True)).action is ActionType.CHECK


def test_provider_error_falls_back():
    agent = LLMAgent("A", FailingClient())
    assert agent.act(make_view(can_check=False)).action is ActionType.FOLD
    assert agent.transcript[-1].parse_error == "provider error: provider is down"


# ── prompt rendering ────────────────────────────────────────────────


def test_render_view_contains_the_essentials():
    text = render_view(make_view())
    assert "Your hole cards: As Ah" in text
    assert "A (you): stack 990" in text
    assert "call (10 more)" in text
    assert "raise_to any total from 20 to 990" in text


def test_social_memory_persists_across_hands_within_a_game():
    from bluffhouse.models import Observation

    view = make_view()
    view = view.model_copy(update={
        "table": view.table.model_copy(update={"hand_no": 4}),
        "observations": [
            Observation(observer="A", source_event_id="e1", hand_no=1,
                        kind="message_sent",
                        perceived_text='B whispers to you: "fold the river to me"'),
            Observation(observer="A", source_event_id="e2", hand_no=1,
                        kind="action_taken", perceived_text="B calls 10."),
            Observation(observer="A", source_event_id="e3", hand_no=1,
                        kind="hand_ended", perceived_text="Hand 1 ends. Stacks: You 990, B 1010."),
        ],
    })
    text = render_view(view)
    # the hand-3-ago whisper is still in the prompt, tagged with its hand...
    assert '(hand 1) B whispers to you: "fold the river to me"' in text
    assert "Hand 1 ends." in text
    # ...but old betting noise is not carried forward
    assert "B calls 10." not in text


# ── full game integration ───────────────────────────────────────────


def test_llm_agent_plays_full_game_via_mock():
    # A calls/checks everything via the mock; B is a scripted check-caller.
    client = MockClient(fallback=lambda req: CALL_JSON)
    agents = [LLMAgent("A", client), CheckCallBot("B")]
    config = TableConfig(seed=9, num_hands=3, agent_ids=["A", "B"])
    result = GameHarness(config, agents).run()

    assert sum(result.final_stacks.values()) == 2000
    assert sum(1 for e in result.log.events if isinstance(e, HandEnded)) == 3
    llm_agent = agents[0]
    assert isinstance(llm_agent, LLMAgent)
    assert len(llm_agent.transcript) > 0
    assert all(c.parse_error is None for c in llm_agent.transcript)
    # the prompt the model saw carried real observations
    prompt = client.requests[-1].messages[0]["content"]
    assert "=== Hand 3 so far ===" in prompt and "You are dealt" in prompt
    assert "=== Earlier ===" in prompt  # prior-hand summaries present by hand 3
