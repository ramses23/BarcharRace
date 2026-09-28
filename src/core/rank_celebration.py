"""Deterministic podium promotions on the existing settled display timeline."""

from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
from math import ceil, cos, pi, sin

from core.bar_value_scale import scale_bar_sprites
from core.transition_timing import sample_timed_sprites


_MAX_RANK = {"off": 0, "first": 1, "top_two": 2, "podium": 3}
_PRESETS = {
    1: (1.0, 17, 100.0, (0.96, 0.65, 0.13)),
    2: (0.8, 12, 76.0, (0.78, 0.86, 0.95)),
    3: (0.65, 8, 57.0, (0.78, 0.39, 0.19)),
}
_SLOT_TOLERANCE = 0.035
_DEPARTURE_TOLERANCE = 0.20


@dataclass(frozen=True)
class RankCelebrationEvent:
    name: str
    rank: int
    frame: int  # Global race frame; opening intro is a fixed offset.


@dataclass(frozen=True)
class ActiveRankCelebration:
    event: RankCelebrationEvent
    age_frames: int
    anchor_sprite: object


class RankCelebrationTimeline:
    def __init__(self, config, sprite_sets, display_timeline, *, events=None):
        self.config = config
        self.sprite_sets = tuple(tuple(row) for row in sprite_sets)
        self.display_timeline = display_timeline
        self.plan = display_timeline.plan
        self.events = self._build_events() if events is None else tuple(events)
        self.frames = tuple(event.frame for event in self.events)
        self._anchor_sprites = {}

    def _build_events(self):
        limit = _MAX_RANK[self.config.rank_celebration]
        if not limit or len(self.sprite_sets) < 2:
            return ()
        events = []
        initial_ranks = dict(self.display_timeline.at(0)[0])
        last_entries = {}
        for index in range(len(self.plan.steps_per_transition)):
            start, end = self.plan.frame_bounds(index)
            previous, previous_count, _ = self.display_timeline._targets(max(0, start - 1))
            rising = {}
            episodes = []
            for frame in range(max(1, start), end):
                current, count, _ = self.display_timeline._targets(frame)
                for name in previous.keys() | current.keys():
                    old_rank = previous.get(name, previous_count)
                    new_rank = current.get(name, count)
                    episode = rising.get(name)
                    if new_rank < old_rank - 1e-8:
                        if episode is None:
                            episode = [name, new_rank, frame, old_rank]
                            rising[name] = episode
                        elif new_rank < episode[1]:
                            attained = round(episode[1])
                            if (0 <= attained < 3 and
                                    abs(episode[1] - attained) <= _SLOT_TOLERANCE):
                                # Preserve each attained slot within this transition;
                                # the settled-dwell check below rejects pass-throughs.
                                episodes.append((*episode, frame - 1, True))
                                rising[name] = [name, new_rank, frame, episode[1]]
                            else:
                                episode[1:3] = (new_rank, frame)
                    elif new_rank > old_rank + 1e-8 and episode is not None:
                        episodes.append((*episode, frame - 1, False))
                        del rising[name]
                previous, previous_count = current, count
            episodes.extend((*episode, end - 1 + self.display_timeline.rank_frames, False)
                            for episode in rising.values())
            for name, attained, first_frame, old_rank, latest, intermediate in episodes:
                rank = round(attained) + 1
                if not (1 <= rank <= limit and
                        abs(attained - (rank - 1)) <= _SLOT_TOLERANCE and
                        old_rank > attained + _DEPARTURE_TOLERANCE):
                    continue
                slot = rank - 1
                key = (name, rank)
                last_entry = last_entries.get(key)
                initial = initial_ranks.get(name)
                armed = last_entry is None and (
                    initial is None or abs(initial - slot) > _DEPARTURE_TOLERANCE)
                search_start = max(first_frame, (last_entry + 1) if last_entry is not None else 1)
                if not armed:
                    for frame in range((last_entry + 1) if last_entry is not None else 1,
                                       search_start):
                        visible = dict(self.display_timeline.at(frame)[0]).get(name)
                        if visible is None or abs(visible - slot) > _DEPARTURE_TOLERANCE:
                            armed = True
                            break
                for frame in range(search_start, min(self.plan.frame_count - 1, latest) + 1):
                    visible = dict(self.display_timeline.at(frame)[0]).get(name)
                    if not armed:
                        if visible is None or abs(visible - slot) > _DEPARTURE_TOLERANCE:
                            armed = True
                        continue
                    target = self.display_timeline._targets(frame)[0].get(name)
                    if target is None or abs(target - slot) > _SLOT_TOLERANCE:
                        continue
                    if visible is None or abs(visible - slot) > _SLOT_TOLERANCE:
                        continue
                    # A direct leap may momentarily pass through intermediate slots.
                    # Count one as a separate stop only if the visible slot remains
                    # settled for two rank-settling intervals before the next ascent.
                    if intermediate and latest - frame + 1 < 2 * self.display_timeline.rank_frames:
                        continue
                    sampled = sample_timed_sprites(
                        self.display_timeline.motion, self.sprite_sets, self.plan, frame)
                    promoted = next((sprite for sprite in sampled if sprite.name == name), None)
                    if promoted is None or promoted.opacity <= 0 or any(
                        sprite.name != name and sprite.opacity > 0
                        and sprite.value == promoted.value for sprite in sampled
                    ):
                        continue
                    events.append(RankCelebrationEvent(name, rank, frame))
                    last_entries[key] = frame
                    break
        return tuple(sorted(events, key=lambda event: (event.frame, event.name)))

    def active_at(self, frame, scale_resolver):
        if not self.events or frame < 0:
            return ()
        longest = ceil(self.config.fps * _PRESETS[1][0])
        stop = bisect_right(self.frames, frame)
        active = []
        for event in self.events[max(0, bisect_right(self.frames, frame - longest)):stop]:
            age = frame - event.frame
            if age >= ceil(self.config.fps * _PRESETS[event.rank][0]):
                continue
            anchor = self._anchor_sprites.get(event)
            if anchor is None:
                raw = sample_timed_sprites(
                    self.display_timeline.motion, self.sprite_sets,
                    self.plan, event.frame)
                scale = scale_resolver.for_sprites(raw, frame_index=event.frame)
                anchor = next((sprite for sprite in scale_bar_sprites(raw, scale, self.config)
                               if sprite.name == event.name), None)
                if anchor is None:
                    continue
                self._anchor_sprites[event] = anchor
            active.append(ActiveRankCelebration(event, age, anchor))
        return tuple(active)


def celebration_particles(event, age_frames, fps, origin):
    """Return fixed-seed (x, y, size, RGBA) particles for one global frame."""
    duration, count, spread, color = _PRESETS[event.rank]
    progress = min(1.0, age_frames / max(1, ceil(duration * fps)))
    envelope = (1.0 - progress) ** 1.4
    points = []
    for index in range(count):
        digest = sha256(f"{event.name}|{event.frame}|{event.rank}|{index}".encode()).digest()
        jitter = (int.from_bytes(digest[:2], "big") / 65535.0 - 0.5) * 0.34
        angle = 2 * pi * (index / count + jitter)
        reach = spread * (0.58 + digest[2] / 510.0) * (0.15 + progress * 0.85)
        x = origin[0] + cos(angle) * reach
        y = origin[1] + sin(angle) * reach + 16 * progress * progress
        size = (40 + digest[3] / 3) * (0.45 + envelope)
        points.append((x, y, size, (*color, envelope * (0.55 + digest[4] / 567.0))))
    return tuple(points)
