from __future__ import annotations

import base64
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import resolve_active_backup_csv


class CsvSourceSelectionTests(unittest.TestCase):
    def test_no_upload_downloads_exact_file_through_file_station(self):
        with TemporaryDirectory() as directory, patch("app.download_daily_csv") as download:
            download.return_value = {
                "name": "abb_daily_result_2026-08-13.csv",
                "content": b"nas-csv",
                "source_type": "file_station_browser_download",
            }
            result = resolve_active_backup_csv(
                {}, {"url": "http://nas.invalid"}, "secret", Path(directory), date(2026, 8, 13)
            )
        self.assertEqual(result, (
            "abb_daily_result_2026-08-13.csv",
            b"nas-csv",
            "file_station_browser_download",
        ))
        download.assert_called_once()

    def test_manual_upload_does_not_open_file_station(self):
        payload = {"active_backup_csv": {
            "name": "abb_daily_result_2026-08-13.csv",
            "content_base64": base64.b64encode(b"manual-csv").decode("ascii"),
        }}
        with TemporaryDirectory() as directory, patch("app.download_daily_csv") as download:
            result = resolve_active_backup_csv(
                payload, {}, "secret", Path(directory), date(2026, 8, 13)
            )
        self.assertEqual(result, (
            "abb_daily_result_2026-08-13.csv",
            b"manual-csv",
            "manual_upload",
        ))
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
