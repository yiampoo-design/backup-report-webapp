from __future__ import annotations

import unittest
from unittest.mock import patch

from synology_web_capture import (
    SynologyWebCaptureError,
    _active_backup_task_list_ready,
    _left_navigation_locator,
    _open_active_backup_task_list,
)


class _Page:
    def __init__(self):
        self.waits: list[int] = []

    def wait_for_timeout(self, value: int) -> None:
        self.waits.append(value)


class _BoxCandidate:
    def __init__(self, x, visible=True):
        self.x = x
        self.visible = visible

    def is_visible(self):
        return self.visible

    def bounding_box(self):
        return {"x": self.x, "y": 0, "width": 50, "height": 20}


class _Matches:
    def __init__(self, candidates):
        self.candidates = candidates

    def count(self):
        return len(self.candidates)

    def nth(self, index):
        return self.candidates[index]


class _Frame:
    def __init__(self, candidates):
        self.candidates = candidates

    def get_by_text(self, text, exact=True):
        return _Matches(self.candidates)


class _FramePage:
    def __init__(self, candidates):
        self.main_frame = _Frame(candidates)
        self.frames = [self.main_frame]


class _Locator:
    def __init__(self, on_click):
        self.on_click = on_click
        self.clicked = False

    def click(self, force=False):
        self.clicked = True
        self.on_click()


class ActiveBackupTaskGridTests(unittest.TestCase):
    def test_grid_columns_are_the_readiness_contract(self):
        required = {"Task Name", "Backup mode", "Device", "Destination", "Last Backup", "Status"}
        with patch(
            "synology_web_capture._visible_exact_text_count",
            side_effect=lambda _page, text, scope=None: 1 if text in required else 0,
        ):
            self.assertTrue(_active_backup_task_list_ready(_Page()))
        with patch(
            "synology_web_capture._visible_exact_text_count",
            side_effect=lambda _page, text, scope=None: 1 if text in {"Task Name", "Last Backup"} else 0,
        ):
            self.assertFalse(_active_backup_task_list_ready(_Page()))

    def test_left_navigation_ignores_overview_card_duplicates(self):
        sidebar = _BoxCandidate(55)
        dashboard_card = _BoxCandidate(600)
        page = _FramePage([dashboard_card, sidebar])
        self.assertIs(_left_navigation_locator(page, "File Server"), sidebar)

    def test_does_not_require_task_list_text_when_grid_is_already_open(self):
        page = _Page()
        with patch("synology_web_capture._active_backup_task_list_ready", return_value=True), patch(
            "synology_web_capture._text_locator"
        ) as text_locator:
            _open_active_backup_task_list(page, None)
        text_locator.assert_not_called()

    def test_clicks_optional_tab_only_when_grid_is_not_open(self):
        page = _Page()
        locator = _Locator(lambda: None)
        with patch("synology_web_capture._active_backup_task_list_ready", side_effect=[False, True]), patch(
            "synology_web_capture._text_locator", return_value=locator
        ):
            _open_active_backup_task_list(page, None)
        self.assertTrue(locator.clicked)
        self.assertEqual(page.waits, [3000])

    def test_fails_closed_when_neither_grid_nor_tab_is_available(self):
        page = _Page()
        with patch("synology_web_capture._active_backup_task_list_ready", return_value=False), patch(
            "synology_web_capture._text_locator", side_effect=SynologyWebCaptureError("missing")
        ), patch("synology_web_capture._save_diagnostic", return_value="diagnostic.png"):
            with self.assertRaisesRegex(SynologyWebCaptureError, "Task Name/Last Backup"):
                _open_active_backup_task_list(page, None)


if __name__ == "__main__":
    unittest.main()
