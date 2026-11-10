"""Tier-Logik: Auf- und Abstieg, Fehlerzustaende.

Reine Funktionen ohne Datenbank, damit sie ohne Netzwerk testbar bleiben.
"""

from . import config


def apply_poll_result(
    tier: str,
    new_hits: int,
    hit_streak: int,
    polls_since_hit: int,
) -> tuple[str, int, int]:
    """Berechnet den neuen Tier nach einem erfolgreichen Poll.

    Rueckgabe: (tier, hit_streak, polls_since_hit)
    """
    if new_hits > 0:
        hit_streak += 1
        polls_since_hit = 0
        if tier == "cold":
            tier = "warm"
        elif tier == "warm" and hit_streak >= config.PROMOTE_AFTER_STREAK:
            tier = "hot"
    else:
        hit_streak = 0
        polls_since_hit += 1
        if tier == "hot" and polls_since_hit >= config.DEMOTE_HOT_AFTER:
            tier = "warm"
        elif tier == "warm" and polls_since_hit >= config.DEMOTE_WARM_AFTER:
            tier = "cold"

    return tier, hit_streak, polls_since_hit


def backoff_seconds(fail_streak: int) -> int:
    """Exponentieller Backoff, gedeckelt bei einer Stunde."""
    return min(3600, 60 * (2 ** max(0, fail_streak - 1)))


def is_dead(fail_streak: int) -> bool:
    return fail_streak >= config.DEAD_AFTER_FAILS


def next_tier_on_cap(tier: str) -> str | None:
    """Ziel-Tier, wenn ein Tier ueber seinem Cap liegt. None = loeschen."""
    order = config.TIER_ORDER
    try:
        index = order.index(tier)
    except ValueError:
        return "cold"
    if index + 1 < len(order):
        return order[index + 1]
    return None
