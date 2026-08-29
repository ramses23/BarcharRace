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
from studio.workspace_paths import ProjectLocation, WorkspaceLayout
from ui.project_studio import _project_display_labels


class ProjectStudioInterfaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="barchart-studio-ui-workspace-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_path = Path(self.temporary_directory.name).resolve()
        self.workspace_root = self.temp_path / "workspace"
        isolated_environment = dict(os.environ)
        isolated_environment.pop("BARCHARTSTUDIO_AUTOLOAD_PROJECT", None)
        isolated_environment.pop("BARCHARTSTUDIO_AUTOLOAD_TOKEN", None)
        isolated_environment["BARCHARTSTUDIO_WORKSPACE"] = str(
            self.workspace_root
        )
        isolated_environment["BARCHARTSTUDIO_SETTINGS_FILE"] = str(
            self.temp_path / "settings" / "settings.json"
        )
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

    def test_project_labels_are_name_first_and_disambiguate_duplicates(self):
        layout = WorkspaceLayout(
            app_root=self.temp_path / "app",
            workspace_root=self.workspace_root,
        )
        production_a = self.workspace_root / "productions" / "alpha"
        production_b = self.workspace_root / "productions" / "beta"
        scratch_root = self.workspace_root / "scratch" / "draft"
        example_root = layout.app_root
        locations = (
            ProjectLocation(
                identifier="production:first",
                absolute_path=production_a / "projects" / "shared.json",
                project_root=production_a,
                relative_path="projects/shared.json",
                kind="production",
                label="unused",
                writable=True,
            ),
            ProjectLocation(
                identifier="production:second",
                absolute_path=production_b / "projects" / "shared.json",
                project_root=production_b,
                relative_path="projects/shared.json",
                kind="production",
                label="unused",
                writable=True,
            ),
            ProjectLocation(
                identifier="example:examples/unique.json",
                absolute_path=example_root / "examples" / "unique.json",
                project_root=example_root,
                relative_path="examples/unique.json",
                kind="example",
                label="unused",
                writable=False,
            ),
            ProjectLocation(
                identifier="scratch:scratch/draft/project.json",
                absolute_path=scratch_root / "project.json",
                project_root=scratch_root,
                relative_path="project.json",
                kind="scratch",
                label="unused",
                writable=True,
            ),
            ProjectLocation(
                identifier="legacy:projects/archive.json",
                absolute_path=example_root / "projects" / "archive.json",
                project_root=example_root,
                relative_path="projects/archive.json",
                kind="legacy",
                label="unused",
                writable=False,
            ),
        )

        labels = _project_display_labels(locations, layout)

        self.assertEqual(
            labels["productions/alpha/projects/shared.json"],
            "shared — Production / alpha",
        )
        self.assertEqual(
            labels["productions/beta/projects/shared.json"],
            "shared — Production / beta",
        )
        self.assertEqual(labels["examples/unique.json"], "unique — Example")
        self.assertEqual(labels["scratch/draft/project.json"], "project — Scratch")
        self.assertEqual(labels["projects/archive.json"], "archive — Legacy")

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

    def test_fun_facts_section_uses_native_controls(self):
        root_dir = Path(__file__).resolve().parents[1]
        app_path = root_dir / "src" / "ui" / "project_studio.py"

        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self.assertFalse(app.exception)
        self._select_editor_section(app, "Fun facts")

        self.assertIn("Enable fun facts", {control.label for control in app.toggle})
        self.assertIn("Source JSON", {control.label for control in app.text_input})
        self.assertIn("Panel width", {control.label for control in app.number_input})

        layout = next(control for control in app.selectbox if control.label == "Layout")
        layout.select("editorial_floating")
        app.run()

        self.assertFalse(app.exception)
        self.assertTrue({
            "Card orientation",
            "Image position",
        }.issubset({control.label for control in app.selectbox}))
        self.assertTrue({
            "Card X",
            "Card Y",
            "Card width",
            "Card height",
            "Bar/card safety gap",
        }.issubset({control.label for control in app.number_input}))
        fields = {control.label: control for control in app.number_input}
        next(
            control
            for control in app.toggle
            if control.label == "Enable fun facts"
        ).set_value(True)
        fields["Card width"].set_value(520)
        fields["Card height"].set_value(260)
        fields["Card X"].set_value(400)
        fields["Card Y"].set_value(300)
        app.run()
        project_data = json.loads(app.json[0].value)
        self.assertEqual(project_data["fun_facts"]["editorial_card_x"], 400)
        self.assertEqual(project_data["fun_facts"]["editorial_card_y"], 300)
        self.assertEqual(project_data["fun_facts"]["editorial_card_width"], 520)
        self.assertEqual(project_data["fun_facts"]["editorial_card_height"], 260)

    def test_date_opacity_updates_the_in_memory_project_draft(self):
        app_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "project_studio.py"
        )
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Canvas")
        opacity = next(
            control for control in app.slider if control.label == "Date opacity"
        )

        self.assertEqual(opacity.value, 22)
        opacity.set_value(65)
        app.run()

        self.assertFalse(app.exception)
        project_data = json.loads(app.json[0].value)
        self.assertEqual(project_data["chart"]["time_label_opacity"], 0.65)

    def test_horizontal_speed_line_controls_persist_in_project_draft(self):
        app_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "project_studio.py"
        )
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Canvas")
        motion = next(
            control
            for control in app.get("button_group")
            if control.label == "Motion"
        )
        self.assertIn("Forward motion", motion.options)
        self.assertIn("Horizontal speed lines", motion.options)
        motion.set_value("horizontal_speed_lines")
        app.run()

        self.assertFalse(app.exception)
        self.assertTrue({
            "Base speed",
            "Base line spacing",
            "Line opacity",
            "Line thickness",
            "Data response strength",
            "Exit compression strength",
        }.issubset({control.label for control in app.slider}))
        self.assertIn(
            "Line color",
            {control.label for control in app.color_picker},
        )
        response = next(
            control
            for control in app.get("button_group")
            if control.label == "Motion response"
        )
        self.assertIn("Second-place acceleration", response.options)
        response.set_value("second_place_acceleration")
        next(
            control for control in app.slider
            if control.label == "Base line spacing"
        ).set_value(800)
        next(
            control for control in app.checkbox
            if control.label == "Left-edge exit compression"
        ).check()
        next(
            control for control in app.slider
            if control.label == "Line thickness"
        ).set_value(5)
        next(
            control for control in app.color_picker
            if control.label == "Line color"
        ).set_value("#12AB34")
        app.run()

        project_data = json.loads(app.json[0].value)
        chart = project_data["chart"]
        self.assertEqual(chart["background_motion"], "horizontal_speed_lines")
        self.assertEqual(
            chart["background_motion_response"],
            "second_place_acceleration",
        )
        self.assertEqual(chart["background_motion_line_spacing"], 800.0)
        self.assertTrue(chart["background_motion_exit_compression"])
        self.assertEqual(chart["background_motion_line_thickness"], 5.0)
        self.assertEqual(chart["background_motion_line_color"], "#12AB34")

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
        with tempfile.TemporaryDirectory():
            app = AppTest.from_file(str(app_path), default_timeout=30).run()
            self._select_editor_section(app, "Export")
            project_file = next(
                control
                for control in app.text_input
                if control.label == "Project JSON"
            )
            project_file.set_value("project.json")
            app.run()

            save_project = next(
                button
                for button in app.button
                if button.label == "Save project"
            )
            save_project.click()
            app.run()

            self.assertFalse(app.exception)
            project_path = (
                Path(app.session_state["active_project_root"])
                / "project.json"
            )
            self.assertTrue(project_path.is_file())
            self.assertTrue(project_path.is_relative_to(self.workspace_root))
            self.assertEqual(
                app.session_state["saved_project_draft_fingerprint"],
                app.session_state["current_project_draft_fingerprint"],
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
        primary_folder = next(
            control.value
            for control in app.text_input
            if control.label == "Logo folder path"
        )
        primary_folder_path = Path(primary_folder)
        self.assertTrue(primary_folder_path.is_absolute())
        self.assertTrue(primary_folder_path.is_relative_to(self.workspace_root))
        self.assertEqual(
            primary_folder_path.parts[-3:],
            ("assets", "logos", folder_name),
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
        primary_logo = Path(project_data["categories"]["Coal"]["logo"])
        self.assertEqual(primary_logo, primary_folder_path / "coal.png")

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
        secondary_folder = next(
            control.value
            for control in app.text_input
            if control.label == "Second logo folder path"
        )
        secondary_folder_path = Path(secondary_folder)
        self.assertTrue(secondary_folder_path.is_absolute())
        self.assertTrue(secondary_folder_path.is_relative_to(self.workspace_root))
        self.assertEqual(
            secondary_folder_path.parts[-3:],
            ("assets", "logos_secondary", folder_name),
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
            Path(project_data["categories"]["Coal"]["logo"]),
            primary_folder_path / "coal.png",
        )
        self.assertEqual(
            Path(project_data["categories"]["Coal"]["secondary_logo"]),
            secondary_folder_path / "coal.png",
        )

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
            ["Data", "Canvas", "Bars", "Fun facts", "Export"],
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

    def test_short_export_controls_persist_range_text_and_resolution(self):
        app_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "project_studio.py"
        )
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Export")

        export_format = next(
            control for control in app.selectbox if control.label == "Format"
        )
        export_format.set_value("short")
        app.run()

        self.assertFalse(app.exception)
        configured_output = next(
            control.value
            for control in app.text_input
            if control.label == "Output MP4"
        )
        self.assertTrue(any(
            "_short.mp4" in caption.value
            for caption in app.caption
            if "Short render output:" in caption.value
        ))
        control_labels = {
            control.label for control in app.selectbox
        } | {
            control.label for control in app.text_input
        }
        self.assertTrue({
            "From", "To", "Intro text", "Context title",
            "Context subtitle", "Outro text",
        }.issubset(control_labels))
        self.assertIn(
            "Estimated duration",
            {metric.label for metric in app.metric},
        )
        self.assertIn(
            "Include Fun Facts in Short",
            {toggle.label for toggle in app.toggle},
        )

        context_title = next(
            control for control in app.text_input if control.label == "Context title"
        )
        context_title.set_value("World's Largest Economies")
        app.run()
        project_data = json.loads(app.json[0].value)

        self.assertEqual(project_data["export"]["mode"], "short")
        self.assertEqual(project_data["export"]["short_width"], 1080)
        self.assertEqual(project_data["export"]["short_height"], 1920)
        self.assertEqual(project_data["chart"]["output_file"], configured_output)
        self.assertEqual(
            project_data["export"]["short_context_title"],
            "World's Largest Economies",
        )

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
            "Date color",
            "Source color",
        }
        self.assertTrue(
            expected_color_labels.issubset(
                {control.label for control in app.color_picker}
            )
        )
        self.assertIn("Image fit", {control.label for control in app.selectbox})

        self.assertTrue({
            "Title opacity", "Subtitle opacity", "Date opacity", "Source opacity",
        }.issubset({control.label for control in app.slider}))

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

    def test_bar_and_fun_fact_text_opacity_and_card_texture_update_draft(self):
        app_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ui"
            / "project_studio.py"
        )
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self._select_editor_section(app, "Bars")
        self.assertTrue({
            "Category color", "Value color", "Ranking color",
        }.issubset({control.label for control in app.color_picker}))
        bar_opacity = {
            control.label: control
            for control in app.slider
            if control.label in {
                "Category opacity", "Value opacity", "Ranking opacity",
            }
        }
        self.assertEqual(set(bar_opacity), {
            "Category opacity", "Value opacity", "Ranking opacity",
        })
        bar_opacity["Category opacity"].set_value(45)
        bar_opacity["Value opacity"].set_value(55)
        bar_opacity["Ranking opacity"].set_value(65)
        app.run()
        data = json.loads(app.json[0].value)
        self.assertEqual(data["chart"]["label_text_opacity"], 0.45)
        self.assertEqual(data["chart"]["value_text_opacity"], 0.55)
        self.assertEqual(data["chart"]["rank_label_text_opacity"], 0.65)

        self._select_editor_section(app, "Fun facts")
        layout = next(control for control in app.selectbox if control.label == "Layout")
        layout.select("editorial_floating")
        app.run()
        texture = next(
            control for control in app.selectbox
            if control.label == "Background texture"
        )
        texture.select("paper")
        app.run()
        sliders = {control.label: control for control in app.slider}
        sliders["Texture intensity"].set_value(35)
        sliders["Headline opacity"].set_value(75)
        sliders["Body opacity"].set_value(65)
        sliders["Credit opacity"].set_value(55)
        app.run()
        self.assertFalse(app.exception)
        data = json.loads(app.json[0].value)
        facts = data["fun_facts"]
        self.assertEqual(facts["editorial_background_texture"], "paper")
        self.assertEqual(facts["editorial_background_texture_intensity"], 0.35)
        self.assertEqual(facts["editorial_headline_opacity"], 0.75)
        self.assertEqual(facts["editorial_body_opacity"], 0.65)
        self.assertEqual(facts["editorial_credit_opacity"], 0.55)


if __name__ == "__main__":
    unittest.main()
