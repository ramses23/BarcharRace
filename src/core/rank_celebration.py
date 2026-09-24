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
    def __init__(self, config, sprite_sets, display_timeline):
        self.config = config
        self.sprite_sets = tuple(tuple(row) for row in sprite_sets)
        self.display_timeline = display_timeline
        self.plan = display_timeline.plan
        self.events = self._build_events()
        self.frames = tuple(event.frame for event in self.events)
        self._anchor_sprites = {}

    def _build_events(self):
        limit = _MAX_RANK[self.config.rank_celebration]
        if not limit or len(self.sprite_sets) < 2:
            return ()
        events = []
        motion = self.display_timeline.motion
        for index, (start, end) in enumerate(zip(self.sprite_sets, self.sprite_sets[1:])):
            old = {sprite.name: sprite for sprite in start if sprite.opacity > 0}
            for finish in end:
                beginning = old.get(finish.name)
                if beginning is None or finish.opacity <= 0:
                    continue
                if beginning.rank is None or finish.rank is None:
                    continue
                rank = int(finish.rank)
                if not (1 <= rank <= limit and finish.rank < beginning.rank):
                    continue
                # A value tie is not a definite promotion, even if name sorting
                # gives the tied rows a deterministic display order.
                if any(other.name != finish.name and other.opacity > 0
                       and other.value == finish.value for other in end):
                    continue
                if any(other.name != beginning.name and other.opacity > 0
                       and other.value == beginning.value for other in start):
                    continue
                completion = max(1, self.plan.frame_at_progress(
                    index, self.config.animation.rank_movement_duration))
                latest = min(self.plan.frame_count - 1,
                             self.plan.prefix_offsets[index + 1]
                             + self.display_timeline.rank_frames - 1)
                for frame in range(completion, latest + 1):
                    target = self.display_timeline._targets(frame)[0].get(finish.name)
                    settled = dict(self.display_timeline.at(frame)[0]).get(finish.name)
                    if target != rank - 1 or settled is None or abs(settled - target) > 1e-7:
                        continue
                    sampled = sample_timed_sprites(motion, self.sprite_sets, self.plan, frame)
                    promoted = next((s for s in sampled if s.name == finish.name), None)
                    if promoted is None or promoted.opacity <= 0 or any(
                        s.name != finish.name and s.opacity > 0 and s.value == promoted.value
                        for s in sampled
                    ):
                        continue
                    events.append(RankCelebrationEvent(finish.name, rank, frame))
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
