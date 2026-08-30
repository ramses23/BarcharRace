from dataclasses import replace
from math import isfinite, pi, sin


RANK_MOTION_FALLING = "falling"
RANK_MOTION_STABLE = "stable"
RANK_MOTION_RISING = "rising"
RANK_MOTION_HEIGHT_EMPHASIS = 4.0
MIN_RANK_MOTION_HEIGHT = 1e-6

_RANK_MOTION_DEPTH = {
    RANK_MOTION_FALLING: -1,
    RANK_MOTION_STABLE: 0,
    RANK_MOTION_RISING: 1,
}


def classify_rank_motion(
    start_rank,
    end_rank,
    *,
    start_present=True,
    end_present=True,
):
    if not start_present and end_present:
        return RANK_MOTION_RISING
    if start_present and not end_present:
        return RANK_MOTION_FALLING
    if start_rank is None or end_rank is None or start_rank == end_rank:
        return RANK_MOTION_STABLE
    if end_rank < start_rank:
        return RANK_MOTION_RISING
    return RANK_MOTION_FALLING


def rank_motion_depth(sprite):
    return _RANK_MOTION_DEPTH.get(
        getattr(sprite, "rank_motion_state", RANK_MOTION_STABLE),
        0,
    )


def rank_motion_sort_key(sprite):
    target_rank = getattr(sprite, "rank_motion_target", None)
    if target_rank is None:
        target_rank = getattr(sprite, "rank", None)
    try:
        target_rank = float(target_rank)
    except (TypeError, ValueError):
        target_rank = float("inf")
    if not isfinite(target_rank):
        target_rank = float("inf")
    name = str(getattr(sprite, "name", ""))
    return (
        rank_motion_depth(sprite),
        target_rank,
        name.casefold(),
        name,
    )


def ordered_rank_motion_sprites(sprites):
    """Draw falling first, stable second, rising last with stable ties."""
    return sorted(sprites, key=rank_motion_sort_key)


def rank_motion_effective_height(sprite):
    base_height = max(MIN_RANK_MOTION_HEIGHT, float(sprite.height))
    state = getattr(sprite, "rank_motion_state", RANK_MOTION_STABLE)
    if state == RANK_MOTION_STABLE:
        return base_height

    progress = min(
        1.0,
        max(0.0, float(getattr(sprite, "rank_motion_progress", 0.0))),
    )
    if progress <= 0.0 or progress >= 1.0:
        return base_height

    delta = RANK_MOTION_HEIGHT_EMPHASIS * sin(pi * progress)
    if state == RANK_MOTION_RISING:
        return base_height + delta
    if state == RANK_MOTION_FALLING:
        return max(MIN_RANK_MOTION_HEIGHT, base_height - delta)
    return base_height


def visual_rank_motion_sprite(sprite):
    """Return render-only body geometry without mutating nominal height."""
    return replace(sprite, height=rank_motion_effective_height(sprite))
