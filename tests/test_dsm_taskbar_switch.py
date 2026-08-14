from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from synology_web_capture import SynologyWebCaptureError, _switch_active_backup_from_taskbar


class _Mouse:
    def __init__(self):
        self.clicks = []

    def click(self, x, y):
        self.clicks.append((x, y))


class _Page:
    def __init__(self):
        self.mouse = _Mouse()
        self.waits = []

    def wait_for_timeout(self, value):
        self.waits.append(value)


class DsmTaskbarSwitchTests(unittest.TestCase):
    def test_clicks_active_backup_taskbar_once_then_validates_navigation(self):
        page = _Page()
        with patch(
            "synology_web_capture._left_navigation_locator",
            side_effect=[SynologyWebCaptureError("hidden"), object()],
        ), patch("synology_web_capture._locator_is_uncovered", return_value=True), patch(
            "synology_web_capture._dismiss_taskbar_preview"
        ):
            _switch_active_backup_from_taskbar(page, Path("diagnostics"))
        self.assertEqual(page.mouse.clicks, [(135, 25)])
        self.assertEqual(page.waits, [1500])

    def test_does_not_toggle_when_active_backup_is_already_visible(self):
        page = _Page()
        with patch("synology_web_capture._left_navigation_locator", return_value=object()), patch(
            "synology_web_capture._locator_is_uncovered", return_value=True
        ):
            _switch_active_backup_from_taskbar(page, Path("diagnostics"))
        self.assertEqual(page.mouse.clicks, [])

    def test_switches_when_navigation_is_visible_but_covered(self):
        page = _Page()
        with patch("synology_web_capture._left_navigation_locator", return_value=object()), patch(
            "synology_web_capture._locator_is_uncovered", side_effect=[False, True]
        ), patch("synology_web_capture._dismiss_taskbar_preview"):
            _switch_active_backup_from_taskbar(page, Path("diagnostics"))
        self.assertEqual(page.mouse.clicks, [(135, 25)])


if __name__ == "__main__":
    unittest.main()
