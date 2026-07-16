import argparse
import csv
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config.bar_selection_config import BarSelectionConfig
from config.chart_config import ChartConfig
from config.data_source_config import DataSourceConfig
from config.dataset_config import DatasetConfig
from config.layout_config import apply_layout_preset
from config.theme_config import get_theme
from config.typography_config import apply_typography_preset
from pipeline.render_job import RenderJob


def main(argv=None):
    args = parse_args(argv)

    if args.csv_output:
        csv_path = Path(args.csv_output)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        generate_synthetic_dataset(
            csv_path,
            start_year=args.start_year,
            years=args.years,
            categories=args.categories,
        )
        return run_profile(args, csv_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "large_profile_dataset.csv"
        generate_synthetic_dataset(
            csv_path,
            start_year=args.start_year,
            years=args.years,
            categories=args.categories,
        )
        return run_profile(args, csv_path)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="profile_large_dataset",
        description="Render a synthetic larger dataset to profile BarChartStudio.",
    )
    parser.add_argument("--years", type=_positive_int, default=30)
    parser.add_argument("--categories", type=_positive_int, default=200)
    parser.add_argument("--start-year", type=int, default=1990)
    parser.add_argument("--top-n", type=_positive_int, default=20)
    parser.add_argument("--steps", type=_positive_int, default=4)
    parser.add_argument("--fps", type=_positive_int, default=6)
    parser.add_argument("--layout", default="youtube_1080p")
    parser.add_argument("--typography", default="compact")
    parser.add_argument("--theme", default="clean_report")
    parser.add_argument("--output", default="output/large_profile.mp4")
    parser.add_argument("--frames-dir", default="output/large_profile_frames")
    parser.add_argument("--csv-output", default=None)
    parser.add_argument("--png-compress-level", type=_png_compress_level, default=1)
    parser.add_argument("--video-crf", type=_non_negative_int, default=23)
    parser.add_argument("--ffmpeg-preset", default="veryfast")

    return parser.parse_args(argv)


def generate_synthetic_dataset(path, start_year=1990, years=30, categories=200):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=("year", "country", "value"))
        writer.writeheader()

        for year_index in range(years):
            year = start_year + year_index

            for category_index in range(categories):
                writer.writerow(
                    {
                        "year": year,
                        "country": f"Category {category_index + 1:03d}",
                        "value": synthetic_value(year_index, category_index, categories),
                    }
                )


def synthetic_value(year_index, category_index, categories):
    base = (categories - category_index) * 1000
    trend = year_index * ((category_index % 9) + 1) * 17
    wave = ((year_index + 3) * (category_index + 5) * 11) % 251
    return round(base + trend + wave, 2)


def run_profile(args, csv_path):
    chart_config = build_chart_config(args)
    data_source_config = DataSourceConfig(
        source_type="csv",
        csv_path=str(csv_path),
    )

    print(
        "Dataset sintetico: "
        f"{args.years} years x {args.categories} categories "
        f"= {args.years * args.categories} rows"
    )

    result = RenderJob(
        config=chart_config,
        data_source_config=data_source_config,
        dataset_config=DatasetConfig(),
    ).run()

    print(
        "Resumen profiling: "
        f"frames={result.frames_rendered}, "
        f"transitions={result.transitions_rendered}, "
        f"total={result.profile.total_seconds:.3f}s"
    )

    return result


def build_chart_config(args):
    chart_config = ChartConfig(
        title="Large Dataset Profile",
        output_file=args.output,
        frames_dir=args.frames_dir,
        fps=args.fps,
        steps_per_transition=args.steps,
        theme=get_theme(args.theme),
        selection=BarSelectionConfig(top_n=args.top_n),
        logos_enabled=False,
        png_compress_level=args.png_compress_level,
        video_crf=args.video_crf,
        ffmpeg_preset=args.ffmpeg_preset,
    )
    chart_config = apply_layout_preset(chart_config, args.layout)
    return apply_typography_preset(chart_config, args.typography)


def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc

    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")

    return parsed


def _png_compress_level(value):
    parsed = _non_negative_int(value)

    if parsed > 9:
        raise argparse.ArgumentTypeError("must be between 0 and 9")

    return parsed


def _non_negative_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc

    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")

    return parsed


if __name__ == "__main__":
    main()
