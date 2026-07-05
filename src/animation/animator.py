import os

from config.chart_config import ChartConfig
from core.layout_engine import LayoutEngine
from models.bar_data import BarData
from models.scene import Scene
from renderer.bar_renderer import BarRenderer


class Animator:
    def __init__(self, renderer: BarRenderer, output_dir="output", config=None):
        self.renderer = renderer
        self.output_dir = output_dir
        self.config = config or ChartConfig()
        self.layout = LayoutEngine(config=self.config)
        os.makedirs(self.output_dir, exist_ok=True)

    def animate_growth(self, bars, steps=30, title="Animation"):
        """
        Genera frames donde los valores crecen progresivamente.
        """
        base_values = [bar.value for bar in bars]

        for i in range(steps):
            progress = (i + 1) / steps

            frame_bars = [
                BarData(
                    name=bar.name,
                    value=base_value * progress,
                    color=bar.color
                )
                for bar, base_value in zip(bars, base_values)
            ]

            sprites = self.layout.build(frame_bars)
            scene = Scene(
                title=title,
                time_label=f"{progress:.0%}",
                bars=sprites,
            )
            filename = self.config.frame_filename(i)

            self.renderer.render(
                scene,
                filename=filename
            )

        print(f"Animacion generada con {steps} frames en {self.output_dir}")
