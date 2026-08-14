from __future__ import annotations

import unittest
from pathlib import Path


class CsvAuditProductionContractTests(unittest.TestCase):
    def test_app_does_not_import_or_call_active_backup_capture(self):
        root = Path(__file__).resolve().parents[1]
        source = root.joinpath("app.py").read_text(encoding="utf-8")
        self.assertNotIn("capture_active_backup", source)
        self.assertIn("download_daily_csv", source)
        self.assertIn('"primary_csv_via_file_station"', source)

    def test_pdf_uses_csv_audit_details_not_dsm_capture(self):
        root = Path(__file__).resolve().parents[1]
        source = root.joinpath("build_backup_report.py").read_text(encoding="utf-8")
        build = source[source.index("def build_pdf"):]
        self.assertIn("legacy_check_elements(row, audit, styles)", build)
        self.assertNotIn("legacy_check_capture_elements(row, audit, styles)", build)


if __name__ == "__main__":
    unittest.main()
