from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from synology_web_capture import _remove_file_station_from_foreground


class _Page:
    def __init__(self):
        self.waits = []

    def wait_for_timeout(self, value):
        self.waits.append(value)


class _Window:
    pass


class DsmForegroundTests(unittest.TestCase):
    def test_minimizes_active_file_station_before_continuing(self):
        page = _Page()
        window = _Window()
        with patch("synology_web_capture._dismiss_restored_settings_dialog", return_value=False), patch(
            "synology_web_capture._active_file_station_window",
            side_effect=[window, None],
        ), patch(
            "synology_web_capture._invoke_ext_window_action",
            return_value={"ok": True, "via": "Ext.minimize", "componentId": "fs"},
        ) as invoke:
            _remove_file_station_from_foreground(page, Path("diagnostics"))

        invoke.assert_called_once_with(window, "minimize")
        self.assertEqual(page.waits, [800])

    def test_source_targets_exact_file_station_active_window(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "synology_web_capture.py"
        ).read_text(encoding="utf-8")
        self.assertIn("div.x-window.syno-sds-fs-win.active-win", source)
        self.assertIn('_invoke_ext_window_action(window, action)', source)
        self.assertIn("Ext.${method}", source)


if __name__ == "__main__":
    unittest.main()
