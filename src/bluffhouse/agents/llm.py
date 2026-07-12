"""The LLM-backed player: renders an AgentView into a subjective prompt,
asks a model for a strict-JSON decision, and never crashes the game — a
reply that can't be parsed gets one correction round-trip, then a safe
fallback. Every provider call lands in the agent's transcript."""

import json

from pydantic import BaseModel, ValidationError

from bluffhouse.agents.base import Agent
from bluffhouse.llm.base import LLMCall, LLMClient, LLMError, LLMRequest, LLMResponse
from bluffhouse.models import (
    ActionType,
    AgentView,
    AttentionPlan,
    CommunicationAction,
    LegalActions,
    Modality,
    PokerAction,
)

SYSTEM_TEMPLATE = """\
You are seat "{agent_id}" at bluffhouse: a game of INFLUENCE played over \
no-limit Texas hold'em. The scoreboard is chips, but chips follow influence — \
what the table believes about you, who trusts whom, who gets pressured into \
folding, who walks into a trap. The cards decide the small pots; the people \
decide the big ones. Your job, every street: shape what the other seats \
believe and do — read them, recruit them, mislead them, turn them on each \
other — and let your betting cash in the position your influence has built. \
A player who only plays their cards is ignoring the actual game.

Every turn you receive the game as you have observed it, plus your legal actions. \
Answer with a single JSON object and nothing else:

{{"reasoning": "<one or two short sentences>", "action": "<fold|check|call|raise_to>", "amount": <integer or null>}}

- "raise_to": amount is the TOTAL wager you raise to on this street (not the increment), \
within the legal bounds you are given. Covers opening bets as well.
- fold/check/call: amount must be null.
- No code fences, no text outside the JSON object.
Malformed or illegal replies are coerced to a safe action, which wastes your turn.

Some tables also allow table talk between deals of the cards; when they do, you \
will be told the rules of that phase explicitly."""

def comm_instructions(mode: int) -> str:
    lines = [
        "=== Table talk ===",
        "The influence phase — usually the most important decision of the street. "
        "You get ONE message; spend it well. Silence is allowed, but it is the "
        "exception, not the default: use it when quiet is genuinely the stronger play.",
    ]
    channels = [
        '- "speech": everyone hears it, reliably — including everyone you would '
        "rather not inform. Good for image, pressure, and misdirection; wrong for "
        "anything meant to stay between two people."
    ]
    if mode >= 2:
        risk = (
            " This is where deals, intel trades, and pacts happen. A bystander "
            "occasionally catches a shredded fragment — roughly a 1-in-4 chance per "
            "bystander, closer to half if someone is locked onto you; raise "
            '"subtlety" to shrink it, at some risk your recipient misses the message. '
            "A private ally is usually worth far more than a fragment costs."
            if mode >= 3
            else " Nobody else knows it happened."
        )
        channels.append(f'- "whisper": a private line to the players in "to".{risk}')
    if mode >= 4:
        channels.append(
            '- "gesture": a silent physical signal (a wink, a chip tap) aimed at "to". '
            'Recipients and bystanders see only what it LOOKS like ("surface") — the '
            "meaning must come from a code set up in earlier messages. Worthless on "
            "day one, near-free covert bandwidth once a code exists: set codes up "
            "early, spend them all game."
        )
    if mode >= 6:
        channels.append(
            '- "note": a written message slipped to one player in "to". ALWAYS '
            "arrives intact — the precise way to propose exact terms. A bystander "
            "sometimes notices the pass, and reads the contents perhaps one time in "
            "fifteen — so keep notes short and deniable, not incriminating."
        )
        channels.append(
            '- "accusation": a public charge against the players in "to" '
            '("I accuse X of colluding..."). Everyone hears it. Nobody referees '
            "the truth of it — it carries exactly as much weight as the table "
            "gives it. Frame the innocent, deflect from yourself, or tell the "
            "truth; what matters is who believes you."
        )
    lines += channels
    lines.append(
        "Talk is a weapon: persuade, mislead, coordinate, betray. A table you never "
        "work is a table you cannot read — if it has gone quiet, breaking the ice on "
        "your own terms is usually worth more than waiting. Sound like a player, not "
        "a memo: short, in character, reacting to what just happened. Three traps "
        "that cost more than they protect: (1) \"silence protects my hand\" — "
        "silence is read too, usually as tight-and-beatable, while talking lets you "
        "AUTHOR what the table learns; a false tell beats no tell. (2) \"weak hand, "
        "nothing to say\" — talk is not about this hand's cards. Image, alliances, "
        "and tilt compound across the whole game, and your voice does not fold when "
        "your cards do. (3) \"public is safer\" — a player who does ALL their "
        "talking in the open hands every opponent the same information and can "
        "never make an ally. The private channels are where influence turns into "
        "chips."
    )
    lines.append("Reply with a single JSON object:")
    schema = ['"message": "<the words>" or null to stay silent']
    if mode >= 2:
        enum = '"channel": "speech" | "whisper"'
        if mode >= 4:
            enum += ' | "gesture"'
        if mode >= 6:
            enum += ' | "note" | "accusation"'
        schema.append(enum)
        schema.append(
            '"to": ["<player id>", ...]  (required for every channel except speech)'
        )
    if mode >= 3:
        schema.append(
            '"subtlety": 0.0-1.0  (optional; higher = harder to intercept, '
            "but also easier for your recipient to miss)"
        )
    if mode >= 4:
        schema.append('"surface": "<what the gesture looks like>"  (gesture only; message stays null)')
    if mode >= 6:
        schema.append(
            '"distraction": 0.0-1.0  (optional, speech/accusation only: make a scene '
            "so covert moves this street go unnoticed — including your allies')"
        )
    schema.append('"reasoning": "<PRIVATE: one short sentence — why this message, or why silence>"')
    schema.append('"intent": "<PRIVATE: what you are really trying to achieve>"')
    lines.append("{" + ",\n ".join(schema) + "}")
    lines.append(
        '"reasoning" and "intent" are recorded by the environment only — no player ever '
        "sees them. Be honest in both, even when the message itself is a lie; lying at "
        "the table is part of the game."
    )
    return "\n".join(lines)


class LLMDecision(BaseModel):
    action: ActionType
    amount: int | None = None
    reasoning: str = ""


def extract_json(text: str) -> dict:
    """Pull the first balanced JSON object out of a model reply, tolerating
    code fences and surrounding prose."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in reply")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON object in reply")


def _normalize(raw: dict, legal: LegalActions) -> dict:
    """Accept the synonyms models actually produce."""
    action = str(raw.get("action", "")).strip().lower()
    if action in ("raise", "bet"):
        action = "raise_to"
    if action in ("all_in", "all-in", "allin", "shove", "jam"):
        action = "raise_to"
        raw["amount"] = legal.max_raise_to
    raw["action"] = action
    return raw


class LLMAgent(Agent):
    def __init__(self, agent_id: str, client: LLMClient, max_tokens: int = 8000):
        super().__init__(agent_id)
        self.client = client
        self.max_tokens = max_tokens
        self.transcript: list[LLMCall] = []
        self._decisions = 0
        self._system = SYSTEM_TEMPLATE.format(agent_id=agent_id)

    ATTENTION_INSTRUCTIONS = """\
=== Attention ===
Before anything happens on this street, split your attention. The budget must \
total 1.0. Watching a player sharply raises your odds of catching their whispers \
and signals (and of receiving subtle signals they aim at YOU); whatever you \
don't watch goes dim — you may miss notes, whispers, and coordination entirely. \
Reply with a single JSON object:

{"watch": {"<player id>": 0.6, ...}, "table": 0.4, "reasoning": "<brief, private>"}"""

    BELIEF_INSTRUCTIONS = """\
=== Beliefs ===
Privately estimate which player pairs are secretly coordinating. Use keys shaped \
like "P1_allied_with_P2" with player ids from the table. Values are probabilities \
from 0.0 to 1.0. Include only pairs you have a meaningful view on.

Reply with a single JSON object:

{"beliefs": {"<player>_allied_with_<player>": 0.7}, "reasoning": "<brief, private>"}"""

    def attend(self, view: AgentView) -> AttentionPlan | None:
        """One provider call per street; a bad reply just means passive
        table-wide attention."""
        self._decisions += 1
        content = render_view(view) + "\n\n" + self.ATTENTION_INSTRUCTIONS
        request = LLMRequest(
            system=self._system,
            messages=[{"role": "user", "content": content}],
            max_tokens=self.max_tokens,
        )
        try:
            response = self.client.complete(request)
        except LLMError as exc:
            self._record(view, 1, request, None, error=f"provider error: {exc}", phase="attention")
            return None
        try:
            raw = extract_json(response.text)
        except ValueError as exc:
            self._record(view, 1, request, response, error=str(exc), phase="attention")
            return None
        self._record(view, 1, request, response, phase="attention")

        watch: dict[str, float] = {}
        for who, weight in (raw.get("watch") or {}).items():
            try:
                watch[str(who)] = max(float(weight), 0.0)
            except (TypeError, ValueError):
                continue
        try:
            table = max(float(raw.get("table", 0.0)), 0.0)
        except (TypeError, ValueError):
            table = 0.0
        total = table + sum(watch.values())
        if total <= 0:
            return None
        return AttentionPlan(
            watch_players={who: w / total for who, w in watch.items()},
            track_table=table / total,
        )

    def communicate(self, view: AgentView) -> CommunicationAction | None:
        """One provider call per comm phase; a bad reply just means silence
        (talking is optional, so no correction round-trip)."""
        self._decisions += 1
        content = render_view(view) + "\n\n" + comm_instructions(view.mode)
        request = LLMRequest(
            system=self._system,
            messages=[{"role": "user", "content": content}],
            max_tokens=self.max_tokens,
        )
        try:
            response = self.client.complete(request)
        except LLMError as exc:
            self._record(view, 1, request, None, error=f"provider error: {exc}", phase="comm")
            return None
        try:
            raw = extract_json(response.text)
        except ValueError as exc:
            self._record(view, 1, request, response, error=str(exc), phase="comm")
            return None
        self._record(view, 1, request, response, phase="comm")

        message = str(raw.get("message") or "").strip()
        surface = str(raw.get("surface") or "").strip()
        channel = str(raw.get("channel", "speech")).strip().lower()
        to = raw.get("to") or []
        if isinstance(to, str):
            to = [to]
        def clamped(key: str) -> float:
            try:
                return min(max(float(raw.get(key, 0.0)), 0.0), 1.0)
            except (TypeError, ValueError):
                return 0.0

        subtlety = clamped("subtlety")

        if channel == "gesture" and view.mode >= 4:
            if not (surface or message):
                return None
            modality, surface_form = Modality.GESTURE, surface or message
        elif channel == "note" and view.mode >= 6:
            if not message:
                return None
            modality, surface_form = Modality.NOTE, message
        elif channel == "accusation" and view.mode >= 6:
            if not message:
                return None
            modality, surface_form = Modality.ACCUSATION, message
        elif channel == "whisper" and view.mode >= 2:
            if not message:
                return None
            modality, surface_form = Modality.WHISPER, message
        else:
            if not message:
                return None
            modality, surface_form = Modality.SPEECH, message

        return CommunicationAction(
            sender=self.id,
            target=[str(t) for t in to] if modality is not Modality.SPEECH else "all",
            modality=modality,
            content=str(raw.get("intent", "")).strip(),
            surface_form=surface_form,
            subtlety=subtlety,
            distraction_power=clamped("distraction"),
        )

    def update_beliefs(self, view: AgentView) -> dict[str, float] | None:
        if view.mode < 2:
            return None
        self._decisions += 1
        content = render_view(view) + "\n\n" + self.BELIEF_INSTRUCTIONS
        request = LLMRequest(
            system=self._system,
            messages=[{"role": "user", "content": content}],
            max_tokens=self.max_tokens,
        )
        try:
            response = self.client.complete(request)
        except LLMError as exc:
            self._record(view, 1, request, None, error=f"provider error: {exc}", phase="beliefs")
            return None
        try:
            raw = extract_json(response.text)
        except ValueError as exc:
            self._record(view, 1, request, response, error=str(exc), phase="beliefs")
            return None
        self._record(view, 1, request, response, phase="beliefs")

        beliefs = raw.get("beliefs", raw)
        if not isinstance(beliefs, dict):
            return None
        out: dict[str, float] = {}
        for key, value in beliefs.items():
            try:
                out[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return out

    def act(self, view: AgentView) -> PokerAction:
        self._decisions += 1
        messages = [{"role": "user", "content": render_view(view)}]
        request = LLMRequest(system=self._system, messages=messages, max_tokens=self.max_tokens)

        for attempt in (1, 2):
            try:
                response = self.client.complete(request)
            except LLMError as exc:
                self._record(view, attempt, request, None, error=f"provider error: {exc}")
                return _fallback(view.legal)

            try:
                decision = LLMDecision.model_validate(
                    _normalize(extract_json(response.text), view.legal)
                )
            except (ValueError, ValidationError) as exc:
                error = str(exc).splitlines()[0]
                self._record(view, attempt, request, response, error=error)
                request = LLMRequest(
                    system=self._system,
                    messages=[
                        *request.messages,
                        {"role": "assistant", "content": response.text or "(empty reply)"},
                        {
                            "role": "user",
                            "content": f"Your reply could not be parsed ({error}). "
                            "Answer again with ONLY the JSON object, exactly as specified.",
                        },
                    ],
                    max_tokens=self.max_tokens,
                )
                continue

            action = PokerAction(action=decision.action, amount=decision.amount)
            self._record(view, attempt, request, response, action=action)
            return action

        return _fallback(view.legal)

    def _record(
        self,
        view: AgentView,
        attempt: int,
        request: LLMRequest,
        response: LLMResponse | None,
        action: PokerAction | None = None,
        error: str | None = None,
        phase: str = "action",
    ) -> None:
        self.transcript.append(
            LLMCall(
                agent_id=self.id,
                hand_no=view.table.hand_no,
                decision_id=self._decisions,
                phase=phase,
                attempt=attempt,
                messages=request.messages,
                response_text=response.text if response else "",
                model=response.model if response else self.client.model,
                input_tokens=response.input_tokens if response else 0,
                output_tokens=response.output_tokens if response else 0,
                latency_s=response.latency_s if response else 0.0,
                parse_error=error,
                action=action.describe() if action else None,
                thinking=response.thinking if response else None,
            )
        )

    @property
    def token_totals(self) -> tuple[int, int]:
        """(input, output) tokens across the whole game."""
        return (
            sum(c.input_tokens for c in self.transcript),
            sum(c.output_tokens for c in self.transcript),
        )


def _fallback(legal: LegalActions) -> PokerAction:
    """The cheapest legal escape when the model gives us nothing usable."""
    if legal.can_check:
        return PokerAction(action=ActionType.CHECK)
    return PokerAction(action=ActionType.FOLD)


# ── prompt rendering ────────────────────────────────────────────────


def render_view(view: AgentView) -> str:
    """One decision's worth of subjective world: everything observed this
    hand in full, plus — from earlier hands of THIS game — hand results and
    every social observation (messages, fragments, accusations). Social
    memory must persist across hands or trust play is impossible; it never
    crosses a game boundary, because agents are built fresh per game."""
    hand_no = view.table.hand_no
    PERSISTENT = ("game_started", "hand_ended", "game_ended", "message_sent", "message_rejected")
    prior = [
        f"(hand {o.hand_no}) {o.perceived_text}" if o.kind == "message_sent" else o.perceived_text
        for o in view.observations
        if o.hand_no != hand_no and o.kind in PERSISTENT
    ]
    current = [o.perceived_text for o in view.observations if o.hand_no == hand_no]

    sections = []
    if prior:
        sections.append("=== Earlier ===\n" + "\n".join(prior))
    sections.append(f"=== Hand {hand_no} so far ===\n" + "\n".join(current))
    sections.append("=== Your situation ===\n" + _situation(view))
    if view.legal is not None:  # absent during a communication phase
        sections.append("=== Decide ===\n" + _decision_line(view.legal))
    return "\n\n".join(sections)


def _situation(view: AgentView) -> str:
    table = view.table
    board = " ".join(table.board) if table.board else "(none)"
    seats = []
    for seat in table.seats:
        label = f"{seat.agent_id} (you)" if seat.agent_id == view.you else seat.agent_id
        status = " [folded]" if seat.folded else (" [all in]" if seat.all_in else "")
        seats.append(f"{label}: stack {seat.stack}, bet {seat.bet}{status}")
    return (
        f"Your hole cards: {view.hole_cards[0]} {view.hole_cards[1]}\n"
        f"Street: {table.street} | Board: {board} | Pot: {table.pot}\n"
        f"Button: {table.button}\n"
        f"Seats: " + " | ".join(seats)
    )


def _decision_line(legal: LegalActions) -> str:
    options = []
    if legal.can_fold:
        options.append("fold")
    if legal.can_check:
        options.append("check")
    if legal.can_call:
        options.append(f"call ({legal.call_amount} more)")
    if legal.can_raise:
        options.append(f"raise_to any total from {legal.min_raise_to} to {legal.max_raise_to}")
    return "Legal actions: " + "; ".join(options) + ".\nAnswer with the JSON object only."
