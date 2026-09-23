from bisect import bisect_right
from math import ceil, isfinite

from models.fun_fact import ActiveFunFact, FunFactCollection, ResolvedFunFact


class FunFactScheduleError(ValueError):
    pass


class FunFactScheduler:
    """Resolve display labels once and select at most one fact per frame."""

    def __init__(self, collection, timeline, *, fade_in=0.20, fade_out=0.20):
        if not isinstance(collection, FunFactCollection):
            raise TypeError("collection must be a FunFactCollection.")
        self.timeline = timeline
        self.fade_in = _fade_value("fade_in", fade_in)
        self.fade_out = _fade_value("fade_out", fade_out)
        if self.fade_in + self.fade_out > 1:
            raise FunFactScheduleError(
                "fun_facts.fade_in plus fun_facts.fade_out must be <= 1."
            )
        self.facts = self._resolve(collection)
        self._facts_by_id = {resolved.fact.id: resolved for resolved in self.facts}
        self._placement_resolver = None
        self._frame_windows = None
        self._display_ends = {}

    def configure_timing(self, periods, plan, fps, *, minimum_seconds=6.0):
        """Extend editorial windows in video time, stopping before the next card.

        Pure global-frame lookup: seeking and partial renders need no history.
        Facts entirely outside an exported period range are not carried into it.
        """
        if not isfinite(fps) or fps <= 0 or not isfinite(minimum_seconds) or minimum_seconds < 0:
            raise ValueError("Fun fact timing requires positive FPS and a finite nonnegative minimum.")
        indices = tuple(self.timeline.get_period_index(p) for p in periods)
        if len(indices) != len(plan.prefix_offsets) or not indices:
            raise ValueError("Fun fact periods must match the timing plan.")
        self._timing_indices = indices
        self._timing_plan = plan
        minimum_frames = ceil(minimum_seconds * fps)
        eligible = [r for r in self.facts
                    if r.end_index >= indices[0] and r.start_index <= indices[-1]]
        windows = []
        self._display_ends = {}
        for i, resolved in enumerate(eligible):
            start = self._frame_for_position(resolved.start_index)
            original_end = self._frame_for_position(resolved.end_index + 1)
            next_start = (self._frame_for_position(eligible[i + 1].start_index)
                          if i + 1 < len(eligible) else plan.frame_count)
            end = min(plan.frame_count, next_start, max(original_end, start + minimum_frames))
            windows.append((resolved, start, end))
            if end >= plan.frame_count:
                end_position = indices[-1] + 1.0
            else:
                index, _, progress = plan.locate(max(0, int(end)))
                end_position = indices[index] + (indices[index + 1] - indices[index]) * progress
            self._display_ends[resolved.fact.id] = end_position
        self._frame_windows = tuple(windows)

    def _frame_for_position(self, position):
        indices, plan = self._timing_indices, self._timing_plan
        if position < indices[0]:
            return 0
        if position > indices[-1]:
            return plan.frame_count
        if position in indices:
            index = indices.index(position)
            return max(0, min(plan.frame_count - 1, plan.prefix_offsets[index]
                              - int(index > 0 and not plan.continuous_motion)))
        index = max(0, bisect_right(indices, position) - 1)
        progress = (position - indices[index]) / (indices[index + 1] - indices[index])
        return plan.frame_at_progress(index, progress)

    def display_end_index(self, resolved):
        """Exclusive display end for smart-placement collision sampling."""
        return self._display_ends.get(resolved.fact.id, resolved.end_index + 1.0)

    def active_at_frame(self, frame_index):
        if self._frame_windows is None:
            raise ValueError("Configure fun fact timing before looking up frames.")
        for resolved, start, end in self._frame_windows:
            if start <= frame_index < end:
                opacity = self._normalized_opacity((frame_index - start) / max(1, end - start))
                return self._active(resolved.fact, opacity) if opacity > 0 else None
        return None

    def set_placement_resolver(self, resolver):
        """Attach an immutable precomputed lookup; no frame history is used."""
        self._placement_resolver = resolver

    def active_at(self, period_a, period_b=None, progress=0.0):
        position = self.timeline.get_timeline_position(
            period_a,
            period_b=period_b,
            progress=progress,
        )
        if self._frame_windows is not None:
            return self.active_at_frame(self._frame_for_position(position))
        for resolved in self.facts:
            end_exclusive = resolved.end_index + 1.0
            if resolved.start_index <= position < end_exclusive:
                opacity = self._opacity(resolved, position)
                if opacity > 0:
                    return self._active(resolved.fact, opacity)
        return None

    def active_for_period(self, period):
        position = self.timeline.get_timeline_position(period) + 0.5
        for resolved in self.facts:
            if resolved.start_index <= position < resolved.end_index + 1.0:
                opacity = self._opacity(resolved, position)
                if opacity > 0:
                    return self._active(resolved.fact, opacity)
        return None

    def force(self, fact_id):
        try:
            fact = self._facts_by_id[str(fact_id)].fact
        except KeyError as exc:
            raise FunFactScheduleError(
                f"Unknown fun fact id {fact_id!r}."
            ) from exc
        return self._active(fact, 1.0, forced=True)

    def _active(self, fact, opacity, *, forced=False):
        position = (
            self._placement_resolver.position_for(fact.id)
            if self._placement_resolver is not None
            else None
        )
        return ActiveFunFact(
            fact=fact,
            opacity=opacity,
            forced=forced,
            resolved_x=(position[0] if position is not None else None),
            resolved_y=(position[1] if position is not None else None),
        )

    def _resolve(self, collection):
        resolved = []
        for fact in collection.facts:
            try:
                start_period = self.timeline.resolve_time_label(fact.start)
            except ValueError as exc:
                raise FunFactScheduleError(
                    f"Fun fact '{fact.id}' field 'start' cannot be resolved: "
                    f"{fact.start!r}."
                ) from exc
            try:
                end_period = self.timeline.resolve_time_label(fact.end)
            except ValueError as exc:
                raise FunFactScheduleError(
                    f"Fun fact '{fact.id}' field 'end' cannot be resolved: "
                    f"{fact.end!r}."
                ) from exc
            start_index = self.timeline.get_period_index(start_period)
            end_index = self.timeline.get_period_index(end_period)
            if start_index > end_index:
                raise FunFactScheduleError(
                    f"Fun fact '{fact.id}' field 'start' occurs after field 'end'."
                )
            resolved.append(ResolvedFunFact(
                fact=fact,
                start_period=start_period,
                end_period=end_period,
                start_index=start_index,
                end_index=end_index,
            ))

        resolved.sort(key=lambda item: (item.start_index, item.end_index, item.fact.id))
        for previous, current in zip(resolved, resolved[1:]):
            if current.start_index <= previous.end_index:
                raise FunFactScheduleError(
                    "Fun facts overlap: "
                    f"'{previous.fact.id}' ({previous.fact.start} to {previous.fact.end}) "
                    f"and '{current.fact.id}' ({current.fact.start} to {current.fact.end})."
                )
        return tuple(resolved)

    def _opacity(self, resolved, position):
        duration = resolved.end_index - resolved.start_index + 1.0
        normalized = (position - resolved.start_index) / duration
        return self._normalized_opacity(normalized)

    def _normalized_opacity(self, normalized):
        normalized = max(0.0, min(1.0, normalized))
        opacity = 1.0
        if self.fade_in > 0 and normalized < self.fade_in:
            opacity = min(opacity, normalized / self.fade_in)
        if self.fade_out > 0 and normalized > 1.0 - self.fade_out:
            opacity = min(opacity, (1.0 - normalized) / self.fade_out)
        return max(0.0, min(1.0, opacity))


def _fade_value(field_name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FunFactScheduleError(f"fun_facts.{field_name} must be numeric.")
    value = float(value)
    if not 0 <= value <= 1:
        raise FunFactScheduleError(f"fun_facts.{field_name} must be from 0 to 1.")
    return value
