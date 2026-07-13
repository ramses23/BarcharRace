import json
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class ProjectStudioInterfaceTest(unittest.TestCase):
    def test_video_duration_estimate_reacts_to_steps_and_fps(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()

        self.assertFalse(app.exception)
        self.assertEqual(
            [tab.label for tab in app.tabs],
            [
                "1. Data & content",
                "2. Canvas & text",
                "3. Bars & categories",
                "4. Animation & output",
            ],
        )
        selectbox_labels = {selectbox.label for selectbox in app.selectbox}
        self.assertNotIn("Theme", selectbox_labels)
        self.assertNotIn("Typography", selectbox_labels)
        self.assertTrue({
            "Time column",
            "Category column",
            "Value column",
            "Canvas layout",
            "Value format",
            "Motion mode",
            "Frame output mode",
        }.issubset(selectbox_labels))
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

    def test_exposes_font_family_selector_for_each_text_element(self):
        app_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "project_studio.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()

        self.assertFalse(app.exception)
        components = [
            json.loads(component.proto.json_args)
            for component in app.get("component_instance")
            if component.proto.component_name == "ui.font_picker.font_family_picker"
        ]
        components_by_label = {
            component["label"]: component
            for component in components
        }
        expected_labels = {
            "Title font",
            "Subtitle font",
            "Category font",
            "Value font",
            "Date font",
            "Source font",
            "Ranking font",
        }

        self.assertEqual(set(components_by_label), expected_labels)

        for label in expected_labels:
            self.assertEqual(
                components_by_label[label]["theme_default_label"],
                "Project default",
            )
            self.assertEqual(len(components_by_label[label]["options"]), 30)
            self.assertIn("DejaVu Sans", components_by_label[label]["options"])

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

        layout_components = [
            json.loads(component.proto.json_args)
            for component in app.get("component_instance")
            if component.proto.component_name == "ui.text_layout_editor.text_layout_editor"
        ]
        self.assertEqual(len(layout_components), 1)
        self.assertEqual(
            set(layout_components[0]["positions"]),
            {"title", "subtitle", "date", "source"},
        )
        self.assertEqual(layout_components[0]["canvas_width"], 1920)
        self.assertEqual(layout_components[0]["canvas_height"], 1080)
        self.assertEqual(
            layout_components[0]["preset_positions"]["title"],
            {"x": 320, "y": 95},
        )

        bar_style_components = [
            json.loads(component.proto.json_args)
            for component in app.get("component_instance")
            if component.proto.component_name == "ui.bar_style_editor.bar_style_editor"
        ]
        self.assertEqual(len(bar_style_components), 1)
        self.assertEqual(
            bar_style_components[0]["settings"]["bar_shape"],
            "rectangle",
        )
        self.assertEqual(
            bar_style_components[0]["settings"]["bar_appearance_mode"],
            "simple",
        )
        self.assertTrue(
            bar_style_components[0]["settings"]["bar_gradient_enabled"]
        )
        self.assertFalse(
            bar_style_components[0]["settings"]["bar_border_enabled"]
        )
        self.assertEqual(len(bar_style_components[0]["bar_colors"]), 3)
        for advanced_field in (
            "bar_fill_type",
            "bar_gradient_direction",
            "bar_texture_preset",
            "bar_bevel_enabled",
            "bar_inner_shadow_opacity",
            "bar_outer_glow_enabled",
            "bar_track_enabled",
            "bar_label_position",
            "bar_label_alignment",
            "bar_value_position",
        ):
            self.assertIn(
                advanced_field,
                bar_style_components[0]["settings"],
            )

        frame_output_mode = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "Frame output mode"
        )
        self.assertEqual(frame_output_mode.value, "ffmpeg_stream")

        title_color = next(
            color_picker
            for color_picker in app.color_picker
            if color_picker.label == "Title color"
        )
        number_inputs["Title size"].set_value(48)
        title_color.set_value("#123456")
        app.run()
        project_data = json.loads(app.json[0].value)

        self.assertEqual(project_data["chart"]["title_font_size"], 48)
        self.assertEqual(project_data["chart"]["title_text_color"], "#123456")
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

        motion_mode = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "Motion mode"
        )
        motion_mode.set_value("continuous")
        app.run()
        project_data = json.loads(app.json[0].value)

        self.assertEqual(project_data["animation"]["motion_mode"], "continuous")

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
