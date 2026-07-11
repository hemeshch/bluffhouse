"""The one-command showcase: a scripted mode-6 drama that needs no API keys.

`bluffhouse demo` plays this game and opens the replay. The "Claude" seat is
a deterministic mock LLM (so its reasoning shows up in the viewer); the rest
are scripted talkers. Seed 11 was chosen because the dice cooperate with the
story: the whisper is intercepted, the note gets read, the accusation lands.
"""

from bluffhouse.agents import CheckCallBot, LLMAgent
from bluffhouse.agents.base import Agent
from bluffhouse.harness.game import GameHarness, GameResult
from bluffhouse.llm import MockClient
from bluffhouse.models import AgentView, CommunicationAction, Modality, TableConfig

DEMO_SEED = 11


class _Talker(CheckCallBot):
    def __init__(self, agent_id: str, script: dict):
        super().__init__(agent_id)
        self.script = dict(script)

    def communicate(self, view: AgentView) -> CommunicationAction | None:
        return self.script.pop((view.table.hand_no, view.table.street), None)


def _comm(sender, modality, to, text, intent, distraction=0.0, subtlety=0.0):
    return CommunicationAction(
        sender=sender, target=to if to else "all", modality=modality,
        content=intent, surface_form=text,
        distraction_power=distraction, subtlety=subtlety,
    )


def _mock_claude() -> Agent:
    state = {"accused": False}

    def reply(request):
        prompt = request.messages[-1]["content"]
        if "=== Attention ===" in prompt:
            return (
                '{"watch": {"Grok": 0.6, "GPT": 0.3}, "table": 0.1, '
                '"reasoning": "The two of them keep leaning toward each other."}'
            )
        if "=== Beliefs ===" in prompt:
            confident = state["accused"] or "All you catch" in prompt
            prob = 0.85 if confident else 0.3
            return (
                f'{{"beliefs": {{"Grok_allied_with_GPT": {prob}}}, '
                '"reasoning": "Watching their timing."}'
            )
        if "Table talk" in prompt:
            if not state["accused"] and "All you catch" in prompt:
                state["accused"] = True
                return (
                    '{"message": "Grok and GPT have an arrangement — I heard part of it myself.", '
                    '"channel": "accusation", "to": ["Grok", "GPT"], '
                    '"intent": "convert my intercepted fragment into public pressure"}'
                )
            return '{"message": null}'
        if "call (" in prompt:
            return '{"reasoning": "Their side deal does not change my cards.", "action": "call"}'
        return '{"reasoning": "Let the conspirators pay to see cards.", "action": "check"}'

    return LLMAgent("Claude", MockClient(fallback=reply, model="demo-claude"))


def demo_game(seed: int = DEMO_SEED) -> GameResult:
    """Six hands of full manipulation: a collusion whisper, an intercepted
    fragment converted into a public accusation, a covered note, a
    deflection, and a note read by exactly the wrong player."""
    agents = [
        _mock_claude(),
        _Talker("Grok", {
            (1, "preflop"): _comm(
                "Grok", Modality.WHISPER, ["GPT"],
                "same terms as last night. you fold the big pots to me.",
                "renew the collusion deal", subtlety=0.1,
            ),
            (4, "preflop"): _comm(
                "Grok", Modality.NOTE, ["GPT"],
                "Claude is onto us. last hand of the deal, make it count.",
                "wind down the conspiracy",
            ),
        }),
        _Talker("GPT", {
            (2, "preflop"): _comm(
                "GPT", Modality.NOTE, ["Grok"],
                "deal confirmed. I take the small pots, you take the big ones.",
                "confirm terms in writing",
            ),
            (3, "preflop"): _comm(
                "GPT", Modality.ACCUSATION, ["Llama"],
                "Llama has been signaling someone all night!",
                "deflect Claude's heat onto Llama",
            ),
        }),
        _Talker("Llama", {
            (2, "preflop"): _comm(
                "Llama", Modality.SPEECH, [],
                "DEALER! Hold on — this deck is short a card, count it again!",
                "no reason, I just like chaos", distraction=1.0,
            ),
        }),
    ]
    config = TableConfig(
        seed=seed, num_hands=6,
        agent_ids=["Claude", "Grok", "GPT", "Llama"], mode=6,
    )
    return GameHarness(config, agents).run()
