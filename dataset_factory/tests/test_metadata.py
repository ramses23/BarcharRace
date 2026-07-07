import unittest

import _test_path
from barchart_dataset_factory.catalog import get_dataset_idea
from barchart_dataset_factory.metadata import (
    DatasetMetadata,
    metadata_template,
    validate_metadata,
)


class MetadataTest(unittest.TestCase):
    def test_builds_template_from_catalog_idea(self):
        idea = get_dataset_idea("fifa_mens_world_ranking")
        metadata = metadata_template(idea)

        self.assertEqual(metadata.dataset_key, "fifa_mens_world_ranking")
        self.assertEqual(metadata.classification, "B")

    def test_validates_required_metadata(self):
        metadata = DatasetMetadata(
            dataset_key="",
            title="Test",
            classification="Z",
            source_name="Source",
            source_url="",
            metric="Metric",
            unit="Units",
            downloaded_at="2026-07-06",
            methodology_note="Method",
        )

        errors = validate_metadata(metadata)

        self.assertIn("classification must be A, B, or C.", errors)
        self.assertIn("dataset_key must be a non-empty string.", errors)


if __name__ == "__main__":
    unittest.main()
