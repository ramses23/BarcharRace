import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4

import _test_path
from PIL import Image
from streamlit.testing.v1 import AppTest


class ProjectStudioInterfaceTest(unittest.TestCase):
    def setUp(self):
        isolated_environment = dict(os.environ)
        isolated_environment.pop("BARCHARTSTUDIO_AUTOLOAD_PROJECT", None)
        isolated_environment.pop("BARCHARTSTUDIO_AUTOLOAD_TOKEN", None)
        self.environment_patcher = mock.patch.dict(
            os.environ,
            isolated_environment,
            clear=True,
        )
        self.environment_patcher.start()
        self.addCleanup(self.environment_patcher.stop)

    def _select_editor_section(self, app, section):
        section_control = next(
            control
            for control in app.get("button_group")
            if control.label == "Editor section"
        )
        section_control.set_value(section)
        app.run()
        self.assertEqual(
            next(
                control.value
                for control in app.get("button_group")
                if control.label == "Editor section"
            ),
            section,
        )

    def test_latest_preview_uses_viewport_controller(self):
        root_dir = Path(__file__).resolve().parents[1]
        studio_source = (
            root_dir / "src" / "ui" / "project_studio.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'floating_preview_controller(key="latest_preview_controller")',
            studio_source,
        )
        self.assertNotIn("apply_studio_layout_styles()", studio_source)

    def test_appearance_presets_save_apply_and_delete_current_visuals(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ,
            {"BARCHARTSTUDIO_APPEARANCE_PRESETS_DIR": temp_dir},
        ), mock.patch(
            "studio.preview.render_project_preview",
            return_value=Path(temp_dir) / "preview.png",
        ):
            Image.new("RGB", (32, 18), "#123456").save(
                Path(temp_dir) / "preview.png"
            )
            app = AppTest.from_file(str(app_path), default_timeout=30).run()
            self._select_editor_section(app, "Canvas")
            title_size = next(
                control
                for control in app.number_input
                if control.label == "Title size"
            )
            title_size.set_value(73)
            app.run()

            preset_name = next(
                control
                for control in app.text_input
                if control.label == "New preset name"
            )
            preset_name.set_value("Reusable documentary")
            app.run()
            save_preset = next(
                button
                for button in app.button
                if button.label == "Save new preset"
            )
            save_preset.click()
            app.run()

            preset_path = Path(temp_dir) / "reusable_documentary.json"
            self.assertFalse(app.exception)
            self.assertTrue(preset_path.is_file())
            self.assertEqual(
                json.loads(preset_path.read_text(encoding="utf-8"))[
                    "canvas"
                ]["title_font_size"],
                73,
            )

            self._select_editor_section(app, "Canvas")
            title_size = next(
                control
                for control in app.number_input
                if control.label == "Title size"
            )
            title_size.set_value(31)
            app.run()
            apply_preset = next(
                button
                for button in app.button
                if button.label == "Apply preset"
            )
            apply_preset.click()
            app.run()

            self.assertFalse(app.exception)
            project_data = json.loads(app.json[0].value)
            self.assertEqual(project_data["chart"]["title_font_size"], 73)
            self.assertTrue(
                any(
                    "Unsaved changes" in caption.value
                    for caption in app.caption
                )
            )

            delete_preset = next(
                button
                for button in app.button
                if button.label == "Delete preset"
            )
            delete_preset.click()
            app.run()
            confirm_delete = next(
                button
                for button in app.button
                if button.label == "Confirm deletion"
            )
            confirm_delete.click()
            app.run()

            self.assertFalse(app.exception)
            self.assertFalse(preset_path.exists())

    def test_project_switch_requires_confirmation_for_unsaved_draft(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        title = next(
            control
            for control in app.text_input
            if control.label == "Video title"
        )
        title.set_value("Unsaved title")
        app.run()

        new_project = next(
            button
            for button in app.button
            if button.label == "New project"
        )
        new_project.click()
        app.run()

        self.assertFalse(app.exception)
        self.assertIn(
            "Discard & continue",
            {button.label for button in app.button},
        )
        self.assertTrue(
            any("unsaved changes" in warning.value.lower() for warning in app.warning)
        )

        keep_editing = next(
            button
            for button in app.button
            if button.label == "Keep editing"
        )
        keep_editing.click()
        app.run()

        self.assertFalse(app.exception)
        self.assertEqual(
            next(
                control.value
                for control in app.text_input
                if control.label == "Video title"
            ),
            "Unsaved title",
        )

    def test_category_editor_filters_and_applies_page_changes(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Bars")

        self.assertFalse(app.exception)
        self.assertIn(
            "Search categories",
            {control.label for control in app.text_input},
        )
        self.assertIn(
            "Category filter",
            {control.label for control in app.selectbox},
        )
        rows_per_page = next(
            control
            for control in app.selectbox
            if control.label == "Rows per page"
        )
        self.assertEqual(rows_per_page.value, 10)

        coal_label = next(
            control
            for control in app.text_input
            if control.label == "Coal"
        )
        coal_label.set_value("Custom Coal")
        apply_changes = next(
            button
            for button in app.button
            if button.label == "Apply category changes"
        )
        apply_changes.click()
        app.run()

        self.assertFalse(app.exception)
        project_data = json.loads(app.json[0].value)
        self.assertEqual(
            project_data["categories"]["Coal"]["label"],
            "Custom Coal",
        )

        search = next(
            control
            for control in app.text_input
            if control.label == "Search categories"
        )
        search.set_value("solar")
        app.run()

        self.assertFalse(app.exception)
        category_labels = {control.label for control in app.text_input}
        self.assertIn("Solar", category_labels)
        self.assertNotIn("Coal", category_labels)

    def test_explicit_save_tracks_unsaved_changes(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / f"ui_save_test_{uuid4().hex}.json"
            app = AppTest.from_file(str(app_path), default_timeout=30).run()
            self._select_editor_section(app, "Export")
            project_file = next(
                control
                for control in app.text_input
                if control.label == "Project JSON"
            )
            project_file.set_value(str(project_path))
            app.run()

            save_project = next(
                button
                for button in app.button
                if button.label == "Save project"
            )
            save_project.click()
            app.run()

            self.assertFalse(app.exception)
            self.assertTrue(project_path.is_file())
            self.assertTrue(
                any("Saved" in caption.value for caption in app.caption)
            )

            self._select_editor_section(app, "Data")
            title = next(
                control
                for control in app.text_input
                if control.label == "Video title"
            )
            title.set_value(f"Changed {uuid4().hex}")
            app.run()

            self.assertFalse(app.exception)
            self.assertTrue(
                any(
                    "Unsaved changes" in caption.value
                    for caption in app.caption
                )
            )

    def test_auto_preview_renders_visual_changes_only(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"

        with tempfile.TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.png"
            Image.new("RGB", (32, 18), "#123456").save(preview_path)

            with mock.patch(
                "studio.preview.render_project_preview",
                return_value=preview_path,
            ) as render_preview:
                app = AppTest.from_file(
                    str(app_path),
                    default_timeout=30,
                ).run()

                self.assertFalse(app.exception)
                self.assertEqual(render_preview.call_count, 0)
                self.assertIn(
                    "Auto preview",
                    {toggle.label for toggle in app.toggle},
                )

                self._select_editor_section(app, "Canvas")
                self.assertEqual(render_preview.call_count, 0)
                title_size = next(
                    control
                    for control in app.number_input
                    if control.label == "Title size"
                )
                title_size.set_value(int(title_size.value) + 1)
                app.run()

                self.assertFalse(app.exception)
                self.assertEqual(render_preview.call_count, 1)
                call_kwargs = render_preview.call_args.kwargs
                self.assertIsInstance(call_kwargs.get("project_data"), dict)
                self.assertEqual(
                    call_kwargs["project_data"]["chart"]["title_font_size"],
                    int(title_size.value),
                )

                self._select_editor_section(app, "Data")
                title = next(
                    control
                    for control in app.text_input
                    if control.label == "Video title"
                )
                title.set_value("Content change without auto render")
                app.run()

                self.assertFalse(app.exception)
                self.assertEqual(render_preview.call_count, 1)

                self._select_editor_section(app, "Export")
                fps = next(
                    control
                    for control in app.number_input
                    if control.label == "FPS"
                )
                fps.set_value(int(fps.value) + 1)
                app.run()

                self.assertFalse(app.exception)
                self.assertEqual(render_preview.call_count, 1)

                self._select_editor_section(app, "Canvas")
                auto_preview = next(
                    toggle
                    for toggle in app.toggle
                    if toggle.label == "Auto preview"
                )
                auto_preview.set_value(False)
                app.run()
                category_size = next(
                    control
                    for control in app.number_input
                    if control.label == "Category size"
                )
                category_size.set_value(int(category_size.value) + 1)
                app.run()

                self.assertFalse(app.exception)
                self.assertEqual(render_preview.call_count, 1)

                auto_preview = next(
                    toggle
                    for toggle in app.toggle
                    if toggle.label == "Auto preview"
                )
                auto_preview.set_value(True)
                app.run()

                self.assertFalse(app.exception)
                self.assertEqual(render_preview.call_count, 2)

    def test_text_visibility_toggles_persist_and_trigger_preview(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"
        labels_to_fields = {
            "Show title": "title_enabled",
            "Show subtitle": "subtitle_enabled",
            "Show date": "time_label_enabled",
            "Show source": "source_label_enabled",
            "Show rankings": "rank_labels_enabled",
            "Show categories": "category_labels_enabled",
            "Show values": "value_labels_enabled",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.png"
            Image.new("RGB", (32, 18), "#123456").save(preview_path)

            with mock.patch(
                "studio.preview.render_project_preview",
                return_value=preview_path,
            ) as render_preview:
                app = AppTest.from_file(
                    str(app_path),
                    default_timeout=30,
                ).run()
                self._select_editor_section(app, "Canvas")

                toggles = {
                    toggle.label: toggle
                    for toggle in app.toggle
                    if toggle.label in labels_to_fields
                }
                self.assertEqual(set(toggles), set(labels_to_fields))
                self.assertTrue(all(toggle.value for toggle in toggles.values()))

                for toggle in toggles.values():
                    toggle.set_value(False)
                app.run()

                self.assertFalse(app.exception)
                project_data = json.loads(app.json[0].value)
                for field in labels_to_fields.values():
                    self.assertFalse(project_data["chart"][field])
                self.assertEqual(render_preview.call_count, 1)
                self.assertFalse(
                    render_preview.call_args.kwargs["project_data"]["chart"][
                        "title_enabled"
                    ]
                )

    def test_logo_folder_and_apply_matches_preserve_unsaved_form_values(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"
        folder_name = f"ui_state_test_{uuid4().hex}"
        uploaded_logo_path = root_dir / "logos" / folder_name / "coal.png"
        uploaded_secondary_logo_path = (
            root_dir / "logos_secondary" / folder_name / "coal.png"
        )

        try:
            app = AppTest.from_file(str(app_path), default_timeout=30).run()
            self._select_editor_section(app, "Canvas")
            title_size = next(
                control
                for control in app.number_input
                if control.label == "Title size"
            )
            title_color = next(
                control
                for control in app.color_picker
                if control.label == "Title color"
            )
            title_size.set_value(73)
            title_color.set_value("#123456")
            app.run()
            self._select_editor_section(app, "Bars")

            logo_folder_upload = next(
                uploader
                for uploader in app.file_uploader
                if uploader.label == "Logo folder"
            )
            logo_folder_upload.set_value([
                (
                    f"{folder_name}/Coal.png",
                    b"test-logo",
                    "image/png",
                )
            ])
            app.run()

            self.assertFalse(app.exception)
            project_data = json.loads(app.json[0].value)
            self.assertEqual(project_data["chart"]["title_font_size"], 73)
            self.assertEqual(project_data["chart"]["title_text_color"], "#123456")
            self.assertEqual(
                next(
                    control.value
                    for control in app.text_input
                    if control.label == "Logo folder path"
                ),
                f"logos/{folder_name}",
            )

            apply_matches = next(
                button
                for button in app.button
                if button.label == "Apply matched logos"
            )
            self.assertFalse(apply_matches.disabled)
            apply_matches.click()
            app.run()

            self.assertFalse(app.exception)
            project_data = json.loads(app.json[0].value)
            self.assertEqual(project_data["chart"]["title_font_size"], 73)
            self.assertEqual(project_data["chart"]["title_text_color"], "#123456")
            self.assertEqual(
                project_data["categories"]["Coal"]["logo"],
                f"logos/{folder_name}/coal.png",
            )

            second_folder_upload = next(
                uploader
                for uploader in app.file_uploader
                if uploader.label == "Second logo folder"
            )
            second_folder_upload.set_value([
                (
                    f"{folder_name}/Coal.png",
                    b"test-second-logo",
                    "image/png",
                )
            ])
            app.run()

            self.assertFalse(app.exception)
            self.assertEqual(
                next(
                    control.value
                    for control in app.text_input
                    if control.label == "Second logo folder path"
                ),
                f"logos_secondary/{folder_name}",
            )
            apply_second_matches = next(
                button
                for button in app.button
                if button.label == "Apply matched second logos"
            )
            self.assertFalse(apply_second_matches.disabled)
            apply_second_matches.click()
            app.run()

            self.assertFalse(app.exception)
            project_data = json.loads(app.json[0].value)
            self.assertEqual(project_data["chart"]["title_text_color"], "#123456")
            self.assertEqual(
                project_data["categories"]["Coal"]["logo"],
                f"logos/{folder_name}/coal.png",
            )
            self.assertEqual(
                project_data["categories"]["Coal"]["secondary_logo"],
                f"logos_secondary/{folder_name}/coal.png",
            )
        finally:
            if uploaded_logo_path.exists():
                uploaded_logo_path.unlink()

            if uploaded_secondary_logo_path.exists():
                uploaded_secondary_logo_path.unlink()

            uploaded_logo_dir = uploaded_logo_path.parent

            if uploaded_logo_dir.exists():
                uploaded_logo_dir.rmdir()

            uploaded_secondary_logo_dir = uploaded_secondary_logo_path.parent

            if uploaded_secondary_logo_dir.exists():
                uploaded_secondary_logo_dir.rmdir()

    def test_video_duration_estimate_reacts_to_steps_and_fps(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()

        self.assertFalse(app.exception)
        section_control = next(
            control
            for control in app.get("button_group")
            if control.label == "Editor section"
        )
        self.assertEqual(
            section_control.options,
            ["Data", "Canvas", "Bars", "Export"],
        )
        self.assertEqual(section_control.value, "Data")
        selectbox_labels = {selectbox.label for selectbox in app.selectbox}
        self.assertNotIn("Theme", selectbox_labels)
        self.assertNotIn("Typography", selectbox_labels)
        self.assertTrue({
            "Time column",
            "Category column",
            "Value column",
        }.issubset(selectbox_labels))

        self._select_editor_section(app, "Canvas")
        self.assertIn(
            "Canvas layout",
            {selectbox.label for selectbox in app.selectbox},
        )
        self._select_editor_section(app, "Bars")
        self.assertIn(
            "Value format",
            {selectbox.label for selectbox in app.selectbox},
        )
        self._select_editor_section(app, "Export")
        self.assertTrue({
            "Motion mode",
            "Frame output mode",
        }.issubset({selectbox.label for selectbox in app.selectbox}))
        initial_metric = next(
            metric
            for metric in app.metric
            if metric.label == "Estimated video duration"
        )
        initial_duration = initial_metric.value
        steps = next(
            control
            for control in app.number_input
            if control.label == "Steps per transition"
        )
        steps.set_value(int(steps.value) * 2)
        app.run()

        doubled_duration = next(
            metric.value
            for metric in app.metric
            if metric.label == "Estimated video duration"
        )
        self.assertNotEqual(doubled_duration, initial_duration)

        fps = next(
            control
            for control in app.number_input
            if control.label == "FPS"
        )
        fps.set_value(int(fps.value) * 2)
        app.run()

        restored_duration = next(
            metric.value
            for metric in app.metric
            if metric.label == "Estimated video duration"
        )
        self.assertEqual(restored_duration, initial_duration)

    def test_value_format_rerun_keeps_only_bars_section_mounted(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Bars")

        value_format = next(
            control
            for control in app.selectbox
            if control.label == "Value format"
        )
        alternate_format = next(
            option
            for option in value_format.options
            if option != value_format.value
        )
        value_format.set_value(alternate_format)
        app.run()

        self.assertFalse(app.exception)
        self.assertEqual(
            next(
                control.value
                for control in app.get("button_group")
                if control.label == "Editor section"
            ),
            "Bars",
        )
        editor_sections = {
            ":material/database: Data and content",
            ":material/dashboard_customize: Canvas and text",
            ":material/bar_chart: Bars and categories",
            ":material/movie_filter: Animation and export",
        }
        visible_sections = {
            subheader.value
            for subheader in app.subheader
            if subheader.value in editor_sections
        }
        self.assertEqual(
            visible_sections,
            {":material/bar_chart: Bars and categories"},
        )

    def test_canvas_layout_change_applies_label_area_preset_defaults(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Canvas")

        layout = next(
            control
            for control in app.selectbox
            if control.label == "Canvas layout"
        )
        layout.set_value("vertical_shorts")
        app.run()

        number_inputs = {
            control.label: control.value
            for control in app.number_input
        }
        self.assertFalse(app.exception)
        self.assertEqual(number_inputs["Bar start"], 260)
        self.assertEqual(number_inputs["Category label start"], 36)
        self.assertEqual(number_inputs["Category area span"], 250)

    def test_canvas_can_use_full_left_space_for_category_labels(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Canvas")

        bar_start = next(
            control
            for control in app.number_input
            if control.label == "Bar start"
        )
        bar_start.set_value(800)
        app.run()

        use_full_space = next(
            button
            for button in app.button
            if button.label == "Use full left space"
        )
        self.assertFalse(use_full_space.disabled)
        use_full_space.click()
        app.run()

        project_data = json.loads(app.json[0].value)
        self.assertFalse(app.exception)
        self.assertEqual(project_data["chart"]["left_margin"], 800)
        self.assertEqual(project_data["chart"]["rank_label_gap"], 704)

    def test_exposes_font_family_selector_for_each_text_element(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()

        self.assertFalse(app.exception)
        subheaders = {subheader.value for subheader in app.subheader}
        self.assertTrue({
            ":material/tune: Project settings",
            ":material/movie_edit: Preview and output",
            ":material/folder_open: Project library",
        }.issubset(subheaders))
        self.assertTrue({
            "Save project",
            "Render preview",
            "Render video",
        }.issubset({button.label for button in app.button}))
        self.assertIn(
            "Project bundle",
            {uploader.label for uploader in app.file_uploader},
        )
        self.assertIn(
            "Prepare portable ZIP",
            {button.label for button in app.button},
        )

        self._select_editor_section(app, "Canvas")
        number_inputs = {
            number_input.label: number_input
            for number_input in app.number_input
        }
        expected_size_labels = {
            "Title size",
            "Subtitle size",
            "Category size",
            "Value size",
            "Date size",
            "Source size",
            "Ranking size",
        }
        self.assertTrue(expected_size_labels.issubset(number_inputs))
        self.assertIn("Category label start", number_inputs)
        self.assertEqual(number_inputs["Category label start"].value, 40)
        self.assertIn("Bar start", number_inputs)
        self.assertEqual(number_inputs["Bar start"].value, 320)
        self.assertIn("Category area span", number_inputs)
        self.assertEqual(number_inputs["Category area span"].value, 320)
        self.assertIn(
            "Background type",
            {control.label for control in app.get("button_group")},
        )
        self.assertIn(
            "Background color",
            {control.label for control in app.color_picker},
        )
        expected_color_labels = {
            "Title color",
            "Subtitle color",
            "Category color",
            "Value color",
            "Date color",
            "Source color",
            "Ranking color",
        }
        self.assertTrue(
            expected_color_labels.issubset(
                {control.label for control in app.color_picker}
            )
        )
        self.assertIn("Image fit", {control.label for control in app.selectbox})

        title_color = next(
            color_picker
            for color_picker in app.color_picker
            if color_picker.label == "Title color"
        )
        number_inputs["Title size"].set_value(48)
        number_inputs["Category label start"].set_value(72)
        number_inputs["Bar start"].set_value(360)
        number_inputs["Category area span"].set_value(340)
        title_color.set_value("#123456")
        app.run()
        project_data = json.loads(app.json[0].value)

        self.assertEqual(project_data["chart"]["title_font_size"], 48)
        self.assertEqual(project_data["chart"]["title_text_color"], "#123456")
        self.assertEqual(project_data["chart"]["label_min_x"], 72)
        self.assertEqual(project_data["chart"]["left_margin"], 360)
        self.assertEqual(project_data["chart"]["rank_label_gap"], 340)
        self.assertEqual(
            project_data["chart"]["frame_output_mode"],
            "ffmpeg_stream",
        )
        self.assertEqual(project_data["chart"]["theme"], "clean_report")
        self.assertEqual(project_data["chart"]["typography_preset"], "editorial")
        self.assertEqual(project_data["chart"]["background_mode"], "color")
        self.assertEqual(
            project_data["chart"]["background_color_override"],
            "#FFFFFF",
        )

        self._select_editor_section(app, "Export")
        frame_output_mode = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "Frame output mode"
        )
        self.assertEqual(frame_output_mode.value, "ffmpeg_stream")
        motion_mode = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "Motion mode"
        )
        motion_mode.set_value("continuous")
        app.run()
        project_data = json.loads(app.json[0].value)

        self.assertEqual(project_data["animation"]["motion_mode"], "continuous")

        self._select_editor_section(app, "Canvas")
        background_type = next(
            control
            for control in app.get("button_group")
            if control.label == "Background type"
        )
        background_type.set_value("image")
        app.run()

        self.assertIn(
            "Upload background image",
            {uploader.label for uploader in app.file_uploader},
        )


if __name__ == "__main__":
    unittest.main()
