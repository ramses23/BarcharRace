import hashlib
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = TESTS_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automation.builders import DatasetBuilder, NationalTeamGoalsDatasetBuilder
from automation.models import DatasetBuildResult
from config.dataset_config import DatasetConfig
from validators.dataset_validator import DatasetValidator


FIXTURE_PATH = (
    Path(__file__).parent
    / "automation"
    / "fixtures"
    / "national_team_goals_source.csv"
)
FIXTURE_SHA256 = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()

ANNUAL_GOLDEN = [
    (2000, "Alpha Republic", 3),
    (2000, "Beta Union", 1),
    (2000, "Old Kingdom (historic)", 1),
    (2001, "Alpha Republic", 0),
    (2001, "Beta Union", 0),
    (2002, "Beta Union", 2),
    (2002, "Gamma Isles", 2),
    (2002, "Alpha Republic", 1),
    (2003, "Gamma Isles", 2),
    (2003, "Alpha Republic", 1),
    (2003, "Beta Union", 1),
]

CUMULATIVE_GOLDEN = [
    (2000, "Alpha Republic", 3),
    (2000, "Beta Union", 1),
    (2000, "Old Kingdom (historic)", 1),
    (2001, "Alpha Republic", 3),
    (2001, "Beta Union", 1),
    (2001, "Old Kingdom (historic)", 1),
    (2002, "Alpha Republic", 4),
    (2002, "Beta Union", 3),
    (2002, "Gamma Isles", 2),
    (2002, "Old Kingdom (historic)", 1),
    (2003, "Alpha Republic", 5),
    (2003, "Beta Union", 4),
    (2003, "Gamma Isles", 4),
    (2003, "Old Kingdom (historic)", 1),
]


class NationalTeamGoalsDatasetBuilderTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name)
        self.builder = NationalTeamGoalsDatasetBuilder()

    def build(self, *, mode="annual", source=FIXTURE_PATH, output_name=None, **kwargs):
        output_name = output_name or f"{mode}.csv"
        return self.builder.build(
            source_csv=source,
            output_csv=self.temp_path / output_name,
            start_year=kwargs.pop("start_year", 2000),
            end_year=kwargs.pop("end_year", 2003),
            mode=mode,
            expected_source_sha256=kwargs.pop(
                "expected_source_sha256", FIXTURE_SHA256
            ),
            duplicate_policy=kwargs.pop("duplicate_policy", "allow"),
            **kwargs,
        )

    @staticmethod
    def rows(path):
        dataframe = pd.read_csv(path)
        return list(dataframe.itertuples(index=False, name=None))

    def write_source(self, name, rows, columns=None):
        path = self.temp_path / name
        dataframe = pd.DataFrame(rows, columns=columns)
        dataframe.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        return path

    def write_source_bytes(self, name, content):
        path = self.temp_path / name
        path.write_bytes(content)
        return path

    def temporary_csv_files(self):
        return list(self.temp_path.glob(".*.tmp"))

    def test_builder_satisfies_common_contract(self):
        builder: DatasetBuilder = self.builder
        self.assertEqual(builder.builder_id, "national_team_goals")
        self.assertEqual(builder.builder_version, "1.0.0")

    def test_result_is_frozen(self):
        result = self.build()
        self.assertIsInstance(result, DatasetBuildResult)
        with self.assertRaises(FrozenInstanceError):
            result.mode = "cumulative"

    def test_annual_output_matches_golden_and_existing_validator(self):
        result = self.build(mode="annual")
        self.assertEqual(self.rows(result.csv_path), ANNUAL_GOLDEN)
        output_bytes = result.csv_path.read_bytes()
        self.assertFalse(output_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(output_bytes.splitlines()[0], b"year,country,value")
        output_frame = pd.read_csv(result.csv_path)
        self.assertTrue(pd.api.types.is_integer_dtype(output_frame["year"]))
        self.assertTrue(pd.api.types.is_integer_dtype(output_frame["value"]))
        validated = DatasetValidator(
            DatasetConfig(
                year_column="year",
                name_column="country",
                value_column="value",
            )
        ).validate(pd.read_csv(result.csv_path))
        self.assertEqual(len(validated), len(ANNUAL_GOLDEN))
        self.assertEqual(result.row_count, len(ANNUAL_GOLDEN))
        self.assertEqual(result.period_count, 4)
        self.assertEqual(result.category_count, 4)

    def test_cumulative_output_matches_golden_and_existing_validator(self):
        result = self.build(mode="cumulative")
        self.assertEqual(self.rows(result.csv_path), CUMULATIVE_GOLDEN)
        validated = DatasetValidator(
            DatasetConfig(
                year_column="year",
                name_column="country",
                value_column="value",
            )
        ).validate(pd.read_csv(result.csv_path))
        self.assertEqual(len(validated), len(CUMULATIVE_GOLDEN))

    def test_cumulative_keeps_flat_years_after_first_positive_value(self):
        rows = self.rows(self.build(mode="cumulative").csv_path)
        alpha = [(year, value) for year, country, value in rows if country == "Alpha Republic"]
        old = [(year, value) for year, country, value in rows if country == "Old Kingdom (historic)"]
        self.assertEqual(alpha[:2], [(2000, 3), (2001, 3)])
        self.assertEqual(old, [(2000, 1), (2001, 1), (2002, 1), (2003, 1)])

    def test_cumulative_omits_years_before_first_positive_value(self):
        rows = self.rows(self.build(mode="cumulative").csv_path)
        gamma_years = [year for year, country, _ in rows if country == "Gamma Isles"]
        self.assertEqual(gamma_years, [2002, 2003])

    def test_exact_historical_and_non_fifa_names_are_preserved(self):
        countries = {country for _, country, _ in self.rows(self.build().csv_path)}
        self.assertIn("Old Kingdom (historic)", countries)
        self.assertIn("Gamma Isles", countries)

    def test_friendlies_tournaments_and_neutral_matches_are_all_included(self):
        rows = self.rows(self.build().csv_path)
        values = {(year, country): value for year, country, value in rows}
        self.assertEqual(values[(2000, "Alpha Republic")], 3)
        self.assertEqual(values[(2002, "Gamma Isles")], 2)
        self.assertEqual(values[(2003, "Alpha Republic")], 1)

    def test_ties_use_category_name_as_deterministic_tiebreaker(self):
        rows = self.rows(self.build(mode="cumulative").csv_path)
        tied = [country for year, country, value in rows if year == 2003 and value == 4]
        self.assertEqual(tied, ["Beta Union", "Gamma Isles"])

    def test_source_hash_and_metadata_are_recorded(self):
        result = self.build()
        self.assertEqual(result.source_sha256, FIXTURE_SHA256)
        self.assertEqual(result.source_size_bytes, FIXTURE_PATH.stat().st_size)
        self.assertEqual(result.matches_read, 9)
        self.assertEqual(result.matches_used, 8)
        self.assertEqual(result.discarded_rows, 1)
        self.assertEqual(result.source_min_date.isoformat(), "2000-01-10")
        self.assertEqual(result.source_max_date.isoformat(), "2004-01-01")
        self.assertIn("matches after end_year", " ".join(result.warnings))

    def test_incorrect_source_hash_fails_without_output(self):
        with self.assertRaisesRegex(ValueError, "Source SHA-256 mismatch"):
            self.build(expected_source_sha256="0" * 64)
        self.assertFalse((self.temp_path / "annual.csv").exists())

    def test_duplicate_policy_error_rejects_repeated_full_match_identity(self):
        with self.assertRaisesRegex(ValueError, "Detected 1 repeated match row"):
            self.build(duplicate_policy="error")

    def test_duplicate_policy_warn_retains_rows_and_records_warning(self):
        result = self.build(duplicate_policy="warn")
        self.assertEqual(self.rows(result.csv_path), ANNUAL_GOLDEN)
        warning = " ".join(result.warnings)
        self.assertIn("Detected 1 repeated match row", warning)
        self.assertIn("tournament", warning)
        self.assertIn("neutral", warning)
        self.assertIn("All rows were retained", warning)

    def test_duplicate_policy_allow_retains_rows_without_duplicate_warning(self):
        result = self.build(duplicate_policy="allow")
        self.assertEqual(self.rows(result.csv_path), ANNUAL_GOLDEN)
        self.assertNotIn("repeated match", " ".join(result.warnings))

    def test_missing_required_columns_fail(self):
        source = self.write_source(
            "missing.csv",
            [["2000-01-01", "Alpha", "Beta", 1]],
            ["date", "home_team", "away_team", "home_score"],
        )
        with self.assertRaisesRegex(ValueError, "Missing required columns: away_score"):
            self.build(source=source, expected_source_sha256=None)

    def test_zero_byte_csv_fails_with_clear_error(self):
        source = self.write_source_bytes("empty.csv", b"")
        with self.assertRaisesRegex(ValueError, "Source CSV has no columns"):
            self.build(source=source, expected_source_sha256=None)
        self.assertFalse((self.temp_path / "annual.csv").exists())
        self.assertEqual(self.temporary_csv_files(), [])

    def test_header_only_csv_fails_with_clear_error(self):
        source = self.write_source_bytes(
            "headers.csv",
            b"date,home_team,away_team,home_score,away_score\n",
        )
        with self.assertRaisesRegex(ValueError, "headers but no match rows"):
            self.build(source=source, expected_source_sha256=None)
        self.assertFalse((self.temp_path / "annual.csv").exists())
        self.assertEqual(self.temporary_csv_files(), [])

    def test_invalid_date_fails(self):
        source = self.write_source(
            "date.csv",
            [["not-a-date", "Alpha", "Beta", 1, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "Invalid date value"):
            self.build(source=source, expected_source_sha256=None)

    def test_null_date_fails(self):
        source = self.write_source(
            "null_date.csv",
            [[None, "Alpha", "Beta", 1, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "Invalid date value"):
            self.build(source=source, expected_source_sha256=None)

    def test_non_integer_score_fails(self):
        source = self.write_source(
            "score.csv",
            [["2000-01-01", "Alpha", "Beta", 1.5, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "non-integer score"):
            self.build(source=source, expected_source_sha256=None)

    def test_null_score_fails(self):
        source = self.write_source(
            "null_score.csv",
            [["2000-01-01", "Alpha", "Beta", None, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "non-integer score"):
            self.build(source=source, expected_source_sha256=None)

    def test_boolean_home_score_fails(self):
        source = self.write_source(
            "boolean_home.csv",
            [["2000-01-01", "Alpha", "Beta", True, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "boolean score.*not valid"):
            self.build(source=source, expected_source_sha256=None)

    def test_boolean_away_score_fails(self):
        source = self.write_source(
            "boolean_away.csv",
            [["2000-01-01", "Alpha", "Beta", 1, False]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "boolean score.*not valid"):
            self.build(source=source, expected_source_sha256=None)

    def test_numpy_boolean_inside_object_scores_fails(self):
        values = pd.Series([np.bool_(True), 1], dtype="object")
        with self.assertRaisesRegex(ValueError, "boolean score.*not valid"):
            self.builder._parse_scores(values, "home_score")

    def test_negative_score_fails(self):
        source = self.write_source(
            "negative.csv",
            [["2000-01-01", "Alpha", "Beta", -1, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "negative score"):
            self.build(source=source, expected_source_sha256=None)

    def test_null_team_name_fails(self):
        source = self.write_source(
            "null_name.csv",
            [["2000-01-01", None, "Beta", 1, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "blank team name"):
            self.build(source=source, expected_source_sha256=None)

    def test_whitespace_only_team_name_fails(self):
        source = self.write_source(
            "blank_name.csv",
            [["2000-01-01", "   ", "Beta", 1, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        with self.assertRaisesRegex(ValueError, "blank team name"):
            self.build(source=source, expected_source_sha256=None)

    def test_outer_team_name_whitespace_is_preserved(self):
        source = self.write_source(
            "spaced_name.csv",
            [["2000-01-01", "  Alpha  ", "Beta", 1, 0]],
            ["date", "home_team", "away_team", "home_score", "away_score"],
        )
        result = self.build(source=source, expected_source_sha256=None)
        self.assertIn((2000, "  Alpha  ", 1), self.rows(result.csv_path))

    def test_invalid_year_interval_fails(self):
        with self.assertRaisesRegex(ValueError, "start_year"):
            self.build(start_year=2004, end_year=2003)

    def test_unknown_mode_and_duplicate_policy_fail(self):
        with self.assertRaisesRegex(ValueError, "mode must be one of"):
            self.build(mode="rolling")
        with self.assertRaisesRegex(ValueError, "duplicate_policy must be one of"):
            self.build(duplicate_policy="drop")

    def test_source_without_matches_in_period_fails(self):
        with self.assertRaisesRegex(ValueError, "No matches exist"):
            self.build(start_year=1990, end_year=1991)

    def test_duplicate_outside_interval_still_fails_with_error_policy(self):
        columns = [
            "date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "tournament",
            "city",
            "country",
            "neutral",
        ]
        outside = [
            "2005-01-01",
            "Gamma",
            "Delta",
            2,
            1,
            "Future Cup",
            "Gamma City",
            "Gamma",
            False,
        ]
        source = self.write_source(
            "outside_duplicate_error.csv",
            [
                ["2000-01-01", "Alpha", "Beta", 1, 0, "Cup", "A", "Alpha", False],
                outside,
                outside,
            ],
            columns,
        )
        with self.assertRaisesRegex(ValueError, "Detected 1 repeated match row"):
            self.build(
                source=source,
                start_year=2000,
                end_year=2000,
                duplicate_policy="error",
                expected_source_sha256=None,
            )

    def test_duplicate_outside_interval_warns_and_is_discarded(self):
        columns = [
            "date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "tournament",
            "city",
            "country",
            "neutral",
        ]
        outside = [
            "2005-01-01",
            "Gamma",
            "Delta",
            2,
            1,
            "Future Cup",
            "Gamma City",
            "Gamma",
            False,
        ]
        source = self.write_source(
            "outside_duplicate_warn.csv",
            [
                ["2000-01-01", "Alpha", "Beta", 1, 0, "Cup", "A", "Alpha", False],
                outside,
                outside,
            ],
            columns,
        )
        result = self.build(
            source=source,
            start_year=2000,
            end_year=2000,
            duplicate_policy="warn",
            expected_source_sha256=None,
        )
        self.assertEqual(result.matches_read, 3)
        self.assertEqual(result.matches_used, 1)
        self.assertEqual(result.discarded_rows, 2)
        self.assertIn("Detected 1 repeated match row", " ".join(result.warnings))

    def test_existing_output_is_never_overwritten(self):
        output = self.temp_path / "annual.csv"
        output.write_text("sentinel", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "already exists"):
            self.build()
        self.assertEqual(output.read_text(encoding="utf-8"), "sentinel")

    def test_concurrent_publication_collision_preserves_foreign_destination(self):
        output = self.temp_path / "annual.csv"

        def create_foreign_destination_then_collide(_source, destination):
            Path(destination).write_text("foreign", encoding="utf-8")
            raise FileExistsError("simulated collision")

        with mock.patch(
            "automation.builders.national_team_goals.os.link",
            side_effect=create_foreign_destination_then_collide,
        ):
            with self.assertRaisesRegex(FileExistsError, "publication collision"):
                self.build()

        self.assertEqual(output.read_text(encoding="utf-8"), "foreign")
        self.assertEqual(self.temporary_csv_files(), [])

    def test_failed_temporary_write_leaves_no_output_or_temporary_file(self):
        with mock.patch.object(
            pd.DataFrame,
            "to_csv",
            side_effect=OSError("simulated write failure"),
        ):
            with self.assertRaisesRegex(OSError, "simulated write failure"):
                self.build()
        self.assertFalse((self.temp_path / "annual.csv").exists())
        self.assertEqual(self.temporary_csv_files(), [])

    def test_failed_hardlink_publication_leaves_no_output_or_temporary_file(self):
        with mock.patch(
            "automation.builders.national_team_goals.os.link",
            side_effect=OSError("publication failed"),
        ):
            with self.assertRaisesRegex(OSError, "hardlink") as context:
                self.build()
        self.assertIsInstance(context.exception.__cause__, OSError)
        self.assertIn("publication failed", str(context.exception.__cause__))
        self.assertFalse((self.temp_path / "annual.csv").exists())
        self.assertEqual(self.temporary_csv_files(), [])

    def test_cleanup_failure_after_successful_hardlink_returns_warning(self):
        with mock.patch.object(
            Path,
            "unlink",
            side_effect=PermissionError("simulated cleanup lock"),
        ):
            result = self.build()

        self.assertTrue(result.csv_path.exists())
        self.assertEqual(self.rows(result.csv_path), ANNUAL_GOLDEN)
        residuals = self.temporary_csv_files()
        self.assertEqual(len(residuals), 1)
        self.assertTrue(residuals[0].exists())
        cleanup_warnings = tuple(
            warning
            for warning in result.warnings
            if "temporary file cleanup failed" in warning
        )
        self.assertEqual(len(cleanup_warnings), 1)
        warning = cleanup_warnings[0]
        self.assertIn("published successfully", warning)
        self.assertIn("simulated cleanup lock", warning)
        warning_path_text = warning.split("residual file: ", 1)[1].rsplit(
            ". Error: ", 1
        )[0]
        warning_path = Path(warning_path_text)
        self.assertTrue(warning_path.exists())
        self.assertTrue(os.path.samefile(warning_path, residuals[0]))
        residuals[0].unlink()

    def test_cleanup_failure_does_not_hide_publication_failure(self):
        with (
            mock.patch(
                "automation.builders.national_team_goals.os.link",
                side_effect=OSError("original link failure"),
            ),
            mock.patch.object(
                Path,
                "unlink",
                side_effect=PermissionError("cleanup lock"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "hardlink") as context:
                self.build()

        self.assertIsInstance(context.exception.__cause__, OSError)
        self.assertIn("original link failure", str(context.exception.__cause__))
        self.assertIn("cleanup also failed", str(context.exception))
        self.assertFalse((self.temp_path / "annual.csv").exists())
        residuals = self.temporary_csv_files()
        self.assertEqual(len(residuals), 1)
        residuals[0].unlink()

    def test_independent_runs_are_byte_identical(self):
        first = self.build(mode="cumulative", output_name="first.csv")
        second = self.build(mode="cumulative", output_name="second.csv")
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertEqual(first.csv_path.read_bytes(), second.csv_path.read_bytes())
        self.assertEqual(
            first.output_sha256,
            hashlib.sha256(first.csv_path.read_bytes()).hexdigest(),
        )

    def test_equivalent_lf_and_crlf_sources_produce_identical_outputs(self):
        header = "date,home_team,away_team,home_score,away_score"
        row = "2000-01-01,Alpha,Beta,2,1"
        lf_source = self.write_source_bytes(
            "lf.csv",
            f"{header}\n{row}\n".encode("utf-8"),
        )
        crlf_source = self.write_source_bytes(
            "crlf.csv",
            f"{header}\r\n{row}\r\n".encode("utf-8"),
        )
        first = self.build(
            source=lf_source,
            expected_source_sha256=None,
            output_name="lf_output.csv",
        )
        second = self.build(
            source=crlf_source,
            expected_source_sha256=None,
            output_name="crlf_output.csv",
        )
        self.assertNotEqual(first.source_sha256, second.source_sha256)
        self.assertEqual(first.output_sha256, second.output_sha256)
        self.assertEqual(first.csv_path.read_bytes(), second.csv_path.read_bytes())

    def test_final_csv_uses_only_lf_line_endings(self):
        output = self.build().csv_path.read_bytes()
        self.assertNotIn(b"\r", output)
        self.assertTrue(output.endswith(b"\n"))

    def test_build_has_zero_network_access(self):
        with (
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("network access attempted"),
            ),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access attempted"),
            ),
        ):
            self.build()


if __name__ == "__main__":
    unittest.main()
