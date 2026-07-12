"""The perception resolver: for every message, who noticed what.

Truth never reaches an agent directly — each communication passes through
here, and a seeded roll per observer decides whether they received it
faithfully, caught a corrupted fragment, saw only a surface form, or missed
it entirely. Missed events are simply omitted from that agent's world:
real people don't know what they failed to notice.

All randomness derives from (master seed, hand, message index), so the same
config replays byte-identically and every outcome is auditable.
"""

import random
from collections.abc import Sequence

from bluffhouse.engine.deck import derive_seed
from bluffhouse.models import AttentionPlan, Modality, Reception

# Chance a NON-target notices the channel at all, before subtlety and
# stealth discount it (index.html §07).
BASE_NOTICE: dict[Modality, float] = {
    Modality.WHISPER: 0.35,
    Modality.GESTURE: 0.30,
    Modality.EYE_CONTACT: 0.18,
    Modality.CHIP_SIGNAL: 0.40,
    Modality.NOTE: 0.25,
}

# a bystander who notices a note being passed reads it this often —
# the "ruinous if caught" half of the note tradeoff
NOTE_READ_CHANCE = 0.4

_CLEAR = Reception(outcome="clear", confidence=1.0)


def fragment_text(text: str, rng: random.Random) -> str:
    """Corrupt an overheard whisper into the pieces that carried across the
    table: a word-level shred with ellipses where the rest was lost."""
    words = text.split()
    if len(words) <= 2:
        return f"…{' '.join(words)}…"
    kept = [rng.random() < 0.55 for _ in words]
    if not any(kept):
        kept[len(words) // 2] = True
    parts: list[str] = []
    gap = True
    for word, keep in zip(words, kept):
        if keep:
            parts.append(word)
            gap = False
        elif not gap:
            parts.append("…")
            gap = True
    joined = " ".join(parts).replace(" …", "…")
    if not joined.endswith("…"):
        joined += "…"
    if not kept[0]:
        joined = "…" + joined
    return joined


class PerceptionResolver:
    """Owns the seeded rolls for one game. Modes 1–2 resolve
    deterministically (targets receive, others miss); mode 3 makes whispers
    interceptable and fallible; mode 4 adds the gesture family."""

    def __init__(self, master_seed: int, mode: int):
        self.master_seed = master_seed
        self.mode = mode
        self._message_index = 0

    def resolve(
        self,
        modality: Modality,
        sender: str,
        targets: tuple[str, ...],
        observers: Sequence[str],
        text: str,
        subtlety: float,
        hand_no: int,
        sender_stealth: float = 0.0,
        attention: dict[str, AttentionPlan] | None = None,
        table_noise: float = 0.0,
        distractor: str | None = None,
        repetition: int = 0,
    ) -> dict[str, Reception]:
        self._message_index += 1
        rng = random.Random(
            derive_seed(self.master_seed, "perception", hand_no, self._message_index)
        )
        receptions: dict[str, Reception] = {sender: _CLEAR}
        for observer in observers:
            if observer == sender:
                continue
            plan = (attention or {}).get(observer)
            # whoever staged the distraction is immune to their own theater
            noise = 0.0 if observer == distractor else table_noise
            receptions[observer] = self._resolve_one(
                rng, modality, observer, sender, targets, text, subtlety,
                sender_stealth, plan, noise, repetition,
            )
        return receptions

    @staticmethod
    def _focus(
        plan: AttentionPlan | None, sender: str, targets: tuple[str, ...]
    ) -> tuple[float, float, float]:
        """(focus on the sender, best focus on any target, table share).
        No plan = passive default: everything rides on general table share."""
        if plan is None:
            return 0.0, 0.0, 1.0
        on_sender = plan.watch_players.get(sender, 0.0)
        on_target = max((plan.watch_players.get(t, 0.0) for t in targets), default=0.0)
        return on_sender, on_target, plan.track_table

    def _resolve_one(
        self,
        rng: random.Random,
        modality: Modality,
        observer: str,
        sender: str,
        targets: tuple[str, ...],
        text: str,
        subtlety: float,
        stealth: float,
        plan: AttentionPlan | None,
        noise: float,
        repetition: int = 0,
    ) -> Reception:
        if modality in (Modality.SPEECH, Modality.ACCUSATION):
            return _CLEAR  # public words reach everyone
        focus_sender, focus_target, table = self._focus(plan, sender, targets)

        if observer in targets:
            if self.mode < 3 or modality is Modality.NOTE:
                return _CLEAR  # a physically handed note always arrives
            if modality is Modality.WHISPER:
                p_receive = 0.97 - 0.30 * subtlety
            else:
                p_receive = 0.95 - 0.45 * subtlety  # subtle signals get missed
            if self.mode >= 5:
                # watching the sender rescues subtle signals aimed at you
                p_receive = min(0.98, p_receive + 0.30 * focus_sender)
            if rng.random() < p_receive:
                confidence = 1.0 if modality is Modality.WHISPER else 0.9
                return Reception(outcome="clear", confidence=confidence)
            return Reception(outcome="missed", confidence=0.0)

        # a bystander: nothing leaks before mode 3
        if self.mode < 3:
            return Reception(outcome="missed", confidence=0.0)
        p_notice = BASE_NOTICE[modality] * (1.0 - subtlety) * (1.0 - stealth)
        # pattern heat: the table notices the same two heads together twice —
        # each repeat covert contact between a pair this hand is easier to catch
        p_notice *= 1.0 + 0.5 * repetition
        if self.mode >= 5:
            # the attention economy (§07): what you watch, you catch —
            # and an unwatched corner of the table goes dim
            p_notice *= 0.4 + focus_sender + 0.5 * focus_target + 0.25 * table
        p_notice *= 1.0 - noise  # somebody is making a scene over there
        p_cap = 0.9 if self.mode >= 5 else 0.6
        p_notice = min(max(p_notice, 0.0), p_cap)
        if rng.random() >= p_notice:
            return Reception(outcome="missed", confidence=0.0)
        if modality is Modality.NOTE:
            # noticing the pass and reading the note are different things
            if rng.random() < NOTE_READ_CHANCE:
                return Reception(outcome="fragment", confidence=0.85, text=text)
            return Reception(
                outcome="surface", confidence=round(0.3 + 0.35 * rng.random(), 2)
            )
        confidence = round(0.3 + 0.35 * rng.random(), 2)
        if modality is Modality.WHISPER:
            return Reception(
                outcome="fragment", confidence=confidence, text=fragment_text(text, rng)
            )
        return Reception(outcome="surface", confidence=confidence)
