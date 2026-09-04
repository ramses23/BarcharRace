"""Isolated worker entry point for large Smart placement precomputes."""

from pathlib import Path
import pickle
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bar_text_geometry import value_text_metric_cache_info
from core.editorial_placement import (
    SmartEditorialPlacementResolver,
    _metric_stats,
    _stream_smart_editorial_placement,
)
from utils.text_fit import install_measurement_font_path_overrides, measurement_font


def main():
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    with input_path.open("rb") as handle:
        task = pickle.load(handle)
    install_measurement_font_path_overrides(
        task.pop("font_path_overrides", None)
    )
    metric_before = value_text_metric_cache_info()
    font_before = measurement_font.cache_info()
    resolved = _stream_smart_editorial_placement(**task)
    resolver = SmartEditorialPlacementResolver(
        resolved._decisions,
        precompute_stats={
            **resolved.precompute_stats,
            **_metric_stats(
                metric_before,
                value_text_metric_cache_info(),
                font_before,
                measurement_font.cache_info(),
            ),
        },
    )
    with output_path.open("wb") as handle:
        pickle.dump(
            (dict(resolver._decisions), dict(resolver.precompute_stats)),
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )


if __name__ == "__main__":
    main()
