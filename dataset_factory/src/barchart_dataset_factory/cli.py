import argparse
import sys

from barchart_dataset_factory.catalog import get_dataset_idea, list_dataset_ideas
from barchart_dataset_factory.metadata import metadata_template, metadata_to_json
from barchart_dataset_factory.validator import DatasetSchema, inspect_csv


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "catalog":
        return print_catalog()

    if args.command == "manifest-template":
        return print_manifest_template(args.dataset_key)

    if args.command in ("inspect", "validate"):
        return inspect_or_validate(args)

    parser.print_help()
    return 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dataset_factory",
        description="Curate and validate datasets for BarChartStudio.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("catalog", help="List known dataset ideas.")

    manifest_parser = subparsers.add_parser(
        "manifest-template",
        help="Print a metadata template for a dataset idea.",
    )
    manifest_parser.add_argument("dataset_key")

    for command in ("inspect", "validate"):
        command_parser = subparsers.add_parser(
            command,
            help=f"{command.capitalize()} a BarChartStudio-compatible CSV.",
        )
        command_parser.add_argument("csv_path")
        command_parser.add_argument("--year-column", default="year")
        command_parser.add_argument("--name-column", default="country")
        command_parser.add_argument("--value-column", default="value")
        command_parser.add_argument(
            "--allow-incomplete-years",
            action="store_true",
            help="Do not warn when a name is missing in some years.",
        )

    return parser


def print_catalog():
    for idea in list_dataset_ideas():
        print(
            f"{idea.key}\tType {idea.classification}\t"
            f"{idea.title}\tMetric: {idea.metric}"
        )

    return 0


def print_manifest_template(dataset_key):
    idea = get_dataset_idea(dataset_key)
    print(metadata_to_json(metadata_template(idea)))
    return 0


def inspect_or_validate(args):
    report = inspect_csv(
        args.csv_path,
        schema=DatasetSchema(
            year_column=args.year_column,
            name_column=args.name_column,
            value_column=args.value_column,
            require_complete_years=not args.allow_incomplete_years,
        ),
    )

    print(f"Rows: {report.rows}")
    print(f"Years: {list(report.years)}")
    print(f"Names: {list(report.names)}")

    for warning in report.warnings:
        print(f"WARNING: {warning}")

    for error in report.errors:
        print(f"ERROR: {error}")

    if args.command == "validate" and not report.ok:
        return 1

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
