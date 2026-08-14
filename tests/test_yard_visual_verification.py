from __future__ import annotations

from io import BytesIO
import inspect
import unittest

from PIL import Image, ImageDraw

from datetime import date

from synology_web_capture import (
    SynologyWebCaptureError,
    _visual_change_ratio,
    _text_locator,
    daily_csv_filename,
    download_daily_csv,
    require_exact_download_name,
)


def png_bytes(with_dialog: bool) -> bytes:
    image = Image.new("RGB", (1000, 580), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 999, 579), outline="navy", width=2)
    if with_dialog:
        draw.rectangle((150, 40, 850, 540), fill="#eeeeee", outline="#555555", width=2)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class YardVisualVerificationTests(unittest.TestCase):
    def test_text_locator_skips_hidden_first_match(self):
        class Candidate:
            def __init__(self, visible):
                self.visible = visible

            def is_visible(self):
                return self.visible

        class Locator:
            candidates = [Candidate(False), Candidate(True)]

            def count(self):
                return len(self.candidates)

            def nth(self, index):
                return self.candidates[index]

        class Frame:
            def get_by_text(self, text, exact=True):
                return Locator()

        class Page:
            main_frame = Frame()
            frames = [main_frame]

        self.assertTrue(_text_locator(Page(), "Download").is_visible())

    def test_identical_images_have_no_change(self):
        before = png_bytes(False)
        self.assertEqual(_visual_change_ratio(before, before), 0.0)

    def test_visible_dialog_is_material_change(self):
        ratio = _visual_change_ratio(png_bytes(False), png_bytes(True))
        self.assertGreater(ratio, 0.02)

    def test_file_station_filename_is_exact_report_date(self):
        self.assertEqual(
            daily_csv_filename(date(2026, 8, 13)),
            "abb_daily_result_2026-08-13.csv",
        )

    def test_file_station_rejects_latest_or_previous_day(self):
        expected = daily_csv_filename(date(2026, 8, 13))
        for observed in (
            "abb_daily_result_latest.csv",
            "abb_daily_result_2026-08-12.csv",
        ):
            with self.subTest(observed=observed):
                with self.assertRaises(SynologyWebCaptureError):
                    require_exact_download_name(expected, observed)

    def test_file_station_path_has_no_api_or_latest_fallback(self):
        source = inspect.getsource(download_daily_csv).casefold()
        self.assertNotIn("synology_api", source)
        self.assertNotIn("latest", source)

    def test_file_station_download_uses_selected_file_context_menu(self):
        source = inspect.getsource(download_daily_csv)
        self.assertIn('target.click(button="right"', source)
        self.assertNotIn("action_button", source)

    def test_file_station_download_menu_is_searched_across_frames(self):
        source = inspect.getsource(download_daily_csv)
        self.assertIn('_text_locator(page, "Download", exact=True)', source)
        self.assertNotIn('page.get_by_text("Download"', source)


if __name__ == "__main__":
    unittest.main()
