from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from app import resolve_task_list_image


class TaskListImageTests(unittest.TestCase):
    def make_png(self, path: Path) -> bytes:
        Image.new("RGB", (640, 360), "white").save(path, "PNG")
        return path.read_bytes()

    def test_optional_image_can_be_omitted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(resolve_task_list_image({}, Path(temp_dir)))

    def test_valid_png_is_saved_inside_report_capture_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            content = self.make_png(root / "source.png")
            result = resolve_task_list_image({
                "task_list_image": {
                    "name": "Task List.png",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
            }, root / "capture")
            self.assertEqual(result, root / "capture" / "task-list.png")
            self.assertEqual(result.read_bytes(), content)

    def test_fake_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "ไม่ใช่ภาพ"):
                resolve_task_list_image({
                    "task_list_image": {
                        "name": "fake.png",
                        "content_base64": base64.b64encode(b"not an image").decode("ascii"),
                    }
                }, Path(temp_dir))

    def test_pdf_places_task_list_before_result_table(self):
        root = Path(__file__).resolve().parents[1]
        source = root.joinpath("build_backup_report.py").read_text(encoding="utf-8")
        build = source[source.index("def build_pdf"):]
        self.assertLess(build.index("task_list_image = Image"), build.index("story.append(legacy_result_table"))

    def test_web_ui_accepts_clipboard_image_without_async_clipboard_api(self):
        root = Path(__file__).resolve().parents[1]
        source = root.joinpath("web", "app.js").read_text(encoding="utf-8")
        html = root.joinpath("web", "index.html").read_text(encoding="utf-8")
        self.assertIn('document.addEventListener("paste",pasteTaskListImage)', source)
        self.assertIn("event.clipboardData", source)
        self.assertNotIn("navigator.clipboard.read", source)
        self.assertIn('id="taskListPreview"', html)
        self.assertIn('id="clearTaskListImage"', html)


if __name__ == "__main__":
    unittest.main()
