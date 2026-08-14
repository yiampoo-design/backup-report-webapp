from __future__ import annotations

import unittest
from unittest.mock import patch

from synology_web_capture import _first_visible, _open_active_backup_details, _open_active_backup_log


class _Candidate:
    def __init__(self, visible=True, enabled=True):
        self.visible = visible
        self.enabled = enabled
        self.clicks = 0
        self.double_clicks = 0

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled

    def click(self, force=False, **kwargs):
        self.clicks += 1

    def dblclick(self, force=False, **kwargs):
        self.double_clicks += 1


class _Locator:
    def __init__(self, candidates):
        self.candidates = candidates

    def count(self):
        return len(self.candidates)

    def nth(self, index):
        return self.candidates[index]


class _Page:
    def __init__(self):
        self.waits = []

    def wait_for_timeout(self, value):
        self.waits.append(value)

    def get_by_role(self, *args, **kwargs):
        return _Locator([])

    def locator(self, *args, **kwargs):
        return _Locator([])

    def get_by_text(self, *args, **kwargs):
        return _Locator([])


class ActiveBackupDetailsTests(unittest.TestCase):
    def test_first_visible_skips_hidden_duplicate(self):
        hidden = _Candidate(visible=False)
        visible = _Candidate(visible=True)
        self.assertIs(_first_visible([_Locator([visible, hidden])]), visible)

    def test_selects_owning_row_before_clicking_enabled_details(self):
        page = _Page()
        row = _Candidate()
        details = _Candidate(enabled=True)
        with patch("synology_web_capture._dismiss_taskbar_preview"), patch(
            "synology_web_capture._locator_is_uncovered", return_value=True
        ), patch("synology_web_capture._switch_active_backup_from_taskbar"), patch(
            "synology_web_capture._task_grid_row", return_value=row
        ), patch(
            "synology_web_capture._first_visible", return_value=details
        ), patch("synology_web_capture._wait_for_active_backup_details", return_value=object()
        ):
            _open_active_backup_details(page, "TASK_1", None)
        self.assertEqual(row.clicks, 1)
        self.assertEqual(details.clicks, 1)
        self.assertEqual(row.double_clicks, 0)

    def test_task_and_details_are_scoped_to_active_backup_window(self):
        page = _Page()
        app_window = _Page()
        row = _Candidate()
        details = _Candidate(enabled=True)
        with patch("synology_web_capture._dismiss_taskbar_preview"), patch(
            "synology_web_capture._locator_is_uncovered", return_value=True
        ), patch("synology_web_capture._switch_active_backup_from_taskbar"), patch(
            "synology_web_capture._task_grid_row", return_value=row
        ) as task_row, patch(
            "synology_web_capture._first_visible", return_value=details
        ), patch("synology_web_capture._wait_for_active_backup_details", return_value=object()):
            _open_active_backup_details(page, "TASK_1", None, app_window)
        task_row.assert_called_once_with(page, "TASK_1", app_window)

    def test_active_backup_core_clicks_are_not_forced(self):
        from pathlib import Path
        source = Path(__file__).resolve().parents[1].joinpath("synology_web_capture.py").read_text(encoding="utf-8")
        details_block = source[source.index("def _open_active_backup_details"):source.index("def _open_active_backup_log")]
        self.assertNotIn("force=True", details_block)

    def test_disabled_details_uses_row_double_click(self):
        page = _Page()
        row = _Candidate()
        details = _Candidate(enabled=False)
        page.screenshot = lambda **kwargs: b"image"
        with patch("synology_web_capture._dismiss_taskbar_preview"), patch(
            "synology_web_capture._locator_is_uncovered", return_value=True
        ), patch("synology_web_capture._switch_active_backup_from_taskbar"), patch(
            "synology_web_capture._task_grid_row", return_value=row
        ), patch(
            "synology_web_capture._first_visible", return_value=details
        ), patch("synology_web_capture._wait_for_active_backup_details", return_value=object()):
            _open_active_backup_details(page, "TASK_1", None)
        self.assertEqual(details.clicks, 0)
        self.assertEqual(row.double_clicks, 1)

    def test_log_is_scoped_to_verified_details_window(self):
        page = _Page()
        log_tab = _Candidate()

        class _Window:
            def get_by_role(self, *args, **kwargs):
                return _Locator([])

            def get_by_text(self, *args, **kwargs):
                return _Locator([log_tab])

            def locator(self, *args, **kwargs):
                return _Locator([])

            def inner_text(self, timeout=None):
                return "Type\nTime\nEvent"

        with patch("synology_web_capture._active_backup_details_window", return_value=_Window()):
            _open_active_backup_log(page, "TASK_1", None)
        self.assertEqual(log_tab.clicks, 1)


if __name__ == "__main__":
    unittest.main()
