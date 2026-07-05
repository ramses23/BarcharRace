from models.bar_data import BarData
from utils.easing import ease_in_out
from utils.interpolation import lerp


class Interpolator:

    def _bars_to_dict(self, bars):
        return {bar.name: bar for bar in bars}

    def interpolate(self, start_bars, end_bars, steps=60):

        start = self._bars_to_dict(start_bars)
        end = self._bars_to_dict(end_bars)

        names = sorted(set(start.keys()) | set(end.keys()))

        frames = []

        for step in range(steps):

            t = ease_in_out(step / (steps - 1))

            current = []

            for name in names:

                start_bar = start.get(name)
                end_bar = end.get(name)

                start_value = start_bar.value if start_bar else 0
                end_value = end_bar.value if end_bar else 0

                color = (
                    start_bar.color
                    if start_bar
                    else end_bar.color
                )

                current.append(
                    BarData(
                        name=name,
                        value=lerp(start_value, end_value, t),
                        color=color
                    )
                )

            current.sort(
                key=lambda bar: bar.value,
                reverse=True
            )

            frames.append(current)

        return frames