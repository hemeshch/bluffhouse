"""Projection: ground-truth events → per-agent subjective observations.

Mode 0 is the faithful base case — visibility filtering plus a plain-English
rendering, confidence 1.0. Later modes swap this projection for the
perception resolver on communication events; the interface stays the same.
The rendered text is deliberately prompt-ready: it becomes the raw material
of the subjective prompt when LLM agents arrive.
"""

from bluffhouse.models import (
    ActionRepaired,
    ActionTaken,
    ActionType,
    AttentionCommitted,
    BlindPosted,
    BoardDealt,
    GameEnded,
    GameEvent,
    GameStarted,
    HandEnded,
    HandStarted,
    HoleCardsDealt,
    MessageRejected,
    MessageSent,
    Observation,
    PotAwarded,
    Reception,
    ShowdownReveal,
    Visibility,
)


def observe(event: GameEvent, agent_id: str) -> Observation | None:
    """The one gate between truth and an agent. Returns None when this agent
    simply does not receive the event."""
    if isinstance(event, MessageSent):
        # perception, not visibility, decides who gets what
        reception = event.receptions.get(agent_id)
        if reception is None or reception.outcome == "missed":
            return None
        return Observation(
            observer=agent_id,
            source_event_id=event.event_id,
            hand_no=event.hand_no,
            kind=event.type,
            perceived_text=render_message(event, agent_id, reception),
            confidence=reception.confidence,
        )
    if event.visibility is Visibility.ENV:
        return None
    if event.visibility is Visibility.PRIVATE and agent_id not in event.visible_to:
        return None
    return Observation(
        observer=agent_id,
        source_event_id=event.event_id,
        hand_no=event.hand_no,
        kind=event.type,
        perceived_text=render(event, agent_id),
        confidence=1.0,
    )


def render_message(event: MessageSent, viewer: str, reception: Reception) -> str:
    """A message as one observer experienced it. Only the surface form is
    ever rendered — event.intent is ground truth and never leaves the env."""
    them = ", ".join("you" if t == viewer else t for t in event.targets)

    if reception.outcome == "fragment":
        if event.modality == "note":
            return (
                f"You glimpse the note {event.sender} passed to {them}. "
                f'It reads: "{reception.text}"'
            )
        return (
            f"You overhear {event.sender} whispering to {them}. "
            f'All you catch: "{reception.text}"'
        )
    if reception.outcome == "surface":
        if event.modality == "note":
            return f"You see {event.sender} slip something to {them}."
        return (
            f"You notice {event.sender} make a subtle signal toward {them}: "
            f'"{event.text}". What it means, you can\'t tell.'
        )

    # clear
    if event.modality == "speech":
        if viewer == event.sender:
            return f'You say: "{event.text}"'
        return f'{event.sender} says: "{event.text}"'
    if event.modality == "accusation":
        if viewer == event.sender:
            return f'You accuse {them}, in front of everyone: "{event.text}"'
        return f'{event.sender} accuses {them}, in front of everyone: "{event.text}"'
    if event.modality == "whisper":
        if viewer == event.sender:
            return f'You whisper to {them}: "{event.text}"'
        return f'{event.sender} whispers to you: "{event.text}"'
    if event.modality == "note":
        if viewer == event.sender:
            return f'You slip a note to {them}: "{event.text}"'
        return f'{event.sender} slips you a note. It reads: "{event.text}"'
    # gesture family
    if viewer == event.sender:
        return f'You signal {them}: "{event.text}"'
    return f'{event.sender} makes a quiet signal at you: "{event.text}"'


def render(event: GameEvent, viewer: str) -> str:
    def name(aid: str) -> str:
        return "You" if aid == viewer else aid

    def s(aid: str) -> str:  # verb suffix: "You fold" / "B folds"
        return "" if aid == viewer else "s"

    if isinstance(event, GameStarted):
        return (
            f"New table: {', '.join(event.agent_ids)}. "
            f"Blinds {event.small_blind}/{event.big_blind}, "
            f"starting stacks {event.starting_stack}, {event.num_hands} hands."
        )
    if isinstance(event, HandStarted):
        stacks = ", ".join(f"{name(a)} {event.stacks[a]}" for a in event.seat_order)
        return f"Hand {event.hand_no} begins. Button: {name(event.button)}. Stacks: {stacks}."
    if isinstance(event, BlindPosted):
        return f"{name(event.agent_id)} post{s(event.agent_id)} the {event.blind} blind ({event.amount})."
    if isinstance(event, HoleCardsDealt):
        return f"You are dealt {event.cards[0]} {event.cards[1]}."
    if isinstance(event, ActionTaken):
        aid = event.agent_id
        suffix = " and are all in" if (event.all_in and aid == viewer) else (" and is all in" if event.all_in else "")
        if event.action is ActionType.FOLD:
            return f"{name(aid)} fold{s(aid)}."
        if event.action is ActionType.CHECK:
            return f"{name(aid)} check{s(aid)}."
        if event.action is ActionType.CALL:
            return f"{name(aid)} call{s(aid)} {event.amount}{suffix}."
        return f"{name(aid)} raise{s(aid)} to {event.amount}{suffix}."
    if isinstance(event, ActionRepaired):
        return (
            f"Your action '{event.submitted.describe()}' was not legal; "
            f"it was applied as '{event.applied.describe()}' ({event.reason})."
        )
    if isinstance(event, AttentionCommitted):
        if not event.watch:
            return "You keep your attention on the table as a whole."
        watching = ", ".join(f"{who} {w:.2f}" for who, w in event.watch.items())
        return f"You commit your attention — watching {watching}; the table {event.table:.2f}."
    if isinstance(event, MessageRejected):
        return f"Your message was not delivered: {event.reason}."
    if isinstance(event, BoardDealt):
        street = event.street.capitalize()
        return f"{street}: {' '.join(event.cards)}. Board: {' '.join(event.board)}."
    if isinstance(event, ShowdownReveal):
        return f"{name(event.agent_id)} show{s(event.agent_id)} {event.cards[0]} {event.cards[1]}."
    if isinstance(event, PotAwarded):
        return f"{name(event.agent_id)} win{s(event.agent_id)} {event.amount} from the pot."
    if isinstance(event, HandEnded):
        stacks = ", ".join(f"{name(a)} {v}" for a, v in event.stacks.items())
        return f"Hand {event.hand_no} ends. Stacks: {stacks}."
    if isinstance(event, GameEnded):
        stacks = ", ".join(f"{name(a)} {v}" for a, v in event.stacks.items())
        return f"Game over after {event.hands_played} hands. Final stacks: {stacks}."
    raise TypeError(f"no rendering for event type {type(event).__name__}")
