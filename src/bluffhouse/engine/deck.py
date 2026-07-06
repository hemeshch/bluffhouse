"""Seeded decks. bluffhouse owns every card that leaves the deck — pokerkit
only ever receives explicit cards — so one master seed reproduces an entire
game, and tests can force exact deals."""

import hashlib
import random
from collections.abc import Sequence

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def standard_deck() -> list[str]:
    return [rank + suit for rank in RANKS for suit in SUITS]


def derive_seed(master: int, *parts: object) -> int:
    """Stable namespaced sub-seed (hash() is salted per process; sha256 is
    stable across runs and platforms)."""
    key = ":".join([str(master), *map(str, parts)])
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


class Deck:
    def __init__(self, cards: Sequence[str]):
        self._cards = list(cards)

    @classmethod
    def seeded(cls, master_seed: int, hand_no: int) -> "Deck":
        rng = random.Random(derive_seed(master_seed, "deck", hand_no))
        cards = standard_deck()
        rng.shuffle(cards)
        return cls(cards)

    @classmethod
    def fixed(cls, prefix: Sequence[str]) -> "Deck":
        """A deck that deals `prefix` in order (including burns), padded with
        the remaining cards so a hand can always run out. For tests."""
        used = set(prefix)
        if len(used) != len(prefix):
            raise ValueError("fixed deck prefix contains duplicates")
        rest = [c for c in standard_deck() if c not in used]
        return cls([*prefix, *rest])

    def draw(self) -> str:
        return self._cards.pop(0)

    def __len__(self) -> int:
        return len(self._cards)
