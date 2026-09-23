"""Stateless display ranking from the values actually shown in a frame."""

from dataclasses import replace

from core.layout_engine import structural_race_vertical_bounds


def position_bars_by_value(sprites, config, settled_ranks=None):
    if not sprites:
        return []
    ordered = sorted(sprites, key=lambda s: (
        config.selection.aggregate_other and s.name == config.selection.other_label,
        -s.value, s.name.casefold(), s.name))
    # Reserve the complete row early in the fade. Using opacity itself leaves
    # two full-height bodies competing for less than two slots for seconds.
    weights = {s.name: min(1.0, max(0.0, s.opacity) / .1) for s in ordered}
    count = max(1.0, sum(weights.values()))
    ratio = config.bar_gap / max(1.0, config.bar_height)
    if config.bar_vertical_layout_mode == "fill_available":
        top, bottom = structural_race_vertical_bounds(config)
        height = max(1.0, (bottom - top) / (count + ratio * max(0.0, count - 1)))
        first = top + height / 2
    else:
        height = float(config.bar_height)
        first = min(s.y for s in sprites)
    pitch = height * (1 + ratio)
    result = []
    target_rank = 0.0
    for sprite in ordered:
        ahead = target_rank
        target_rank += weights[sprite.name]
        if settled_ranks is not None:
            ahead = settled_ranks.get(sprite.name, ahead)
        # An entering row starts below the current rows, not at its future rank.
        entry_offset = (1 - weights[sprite.name]) * count * pitch
        result.append(replace(sprite, y=first + ahead * pitch + entry_offset,
                              height=height, rank=1 + ahead))
    return result
