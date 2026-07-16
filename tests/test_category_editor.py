import unittest

import _test_path
from ui.category_editor import (
    filter_categories,
    paginate_categories,
    update_category_style,
)


class CategoryEditorTest(unittest.TestCase):
    def test_filters_by_raw_name_and_custom_label(self):
        categories = ("DEU", "MEX", "USA")
        styles = {"DEU": {"label": "Germany"}, "MEX": {"label": "México"}}

        self.assertEqual(filter_categories(categories, styles, "mex"), ("MEX",))
        self.assertEqual(filter_categories(categories, styles, "germany"), ("DEU",))

    def test_filters_customized_and_missing_logos(self):
        categories = ("A", "B", "C")
        styles = {
            "A": {"color": "#123456", "logo": "logos/a.png"},
            "B": {"secondary_logo": "flags/b.png"},
        }

        self.assertEqual(
            filter_categories(categories, styles, category_filter="Customized"),
            ("A", "B"),
        )
        self.assertEqual(
            filter_categories(
                categories,
                styles,
                category_filter="Missing primary logo",
            ),
            ("B", "C"),
        )
        self.assertEqual(
            filter_categories(
                categories,
                styles,
                category_filter="Missing second logo",
            ),
            ("A", "C"),
        )

    def test_paginates_and_clamps_page(self):
        categories = tuple(f"Category {index}" for index in range(23))

        second = paginate_categories(categories, page=2, page_size=10)
        beyond_last = paginate_categories(categories, page=99, page_size=10)

        self.assertEqual(second.items[0], "Category 10")
        self.assertEqual((second.start, second.end), (11, 20))
        self.assertEqual(second.page_count, 3)
        self.assertEqual(beyond_last.page, 3)
        self.assertEqual((beyond_last.start, beyond_last.end), (21, 23))

    def test_empty_page_has_stable_metadata(self):
        page = paginate_categories((), page=3, page_size=10)

        self.assertEqual(page.items, ())
        self.assertEqual(page.page, 1)
        self.assertEqual(page.page_count, 1)
        self.assertEqual((page.start, page.end), (0, 0))

    def test_updates_known_fields_and_preserves_future_fields(self):
        styles = {
            "A": {
                "label": "Old",
                "logo": "old.png",
                "future_setting": "preserve",
            }
        }

        updated = update_category_style(
            styles,
            "A",
            label="Alpha",
            use_color=True,
            color="#123456",
            logo="logos/a.png",
            secondary_logo="flags/a.png",
        )

        self.assertEqual(
            updated["A"],
            {
                "label": "Alpha",
                "color": "#123456",
                "logo": "logos/a.png",
                "secondary_logo": "flags/a.png",
                "future_setting": "preserve",
            },
        )

    def test_removes_empty_known_style(self):
        updated = update_category_style(
            {"A": {"label": "Alpha", "color": "#123456"}},
            "A",
            label="A",
        )

        self.assertNotIn("A", updated)


if __name__ == "__main__":
    unittest.main()
