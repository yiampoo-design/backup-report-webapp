from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

from csv_report import BANGKOK, parse_uploaded_daily_csv


CSV_BYTES = """No.,Group,Backup Task,Status,Source,Last Backup,Duration,Size,File Count,Warning/Error,Unchanged,Same Size,Audit Same Size,Audit Status,Note
1,File Backup,TEST_Backup,Successful,192.0.2.10,13/08/2026 00:00:06,00:03:38,3.56 MB,1151,0 / 0,37133,3,3 of 3,Check,Size/File Count unchanged

AUDIT
พบ 1 Task เข้าเงื่อนไขตรวจสอบ

Audit 1 - File Backup
TEST_Backup

รายการ,ผล
Backup Status,Successful
Source,192.0.2.10
Last Backup,13/08/2026 00:00:06
Backup Size,3.56 MB
File Count,1151
Audit Same Size,3 of 3
Audit Result,CHECK
ผลตรวจสอบ,ข้อมูลจาก NAS ต้องได้รับการตรวจสอบ
""".encode("utf-8")


class UploadedDailyCsvTests(unittest.TestCase):
    filename = "abb_daily_result_2026-08-13.csv"
    now = datetime(2026, 8, 13, 9, 5, tzinfo=BANGKOK)

    def test_uploaded_csv_is_the_only_table_source(self):
        rows, audit = parse_uploaded_daily_csv(CSV_BYTES, self.filename, now=self.now)
        self.assertEqual(audit["source_type"], "manual_csv_upload")
        self.assertEqual(audit["result_path"], self.filename)
        self.assertEqual(rows[0]["Start"], "2026-08-13 00:00:06")
        self.assertNotIn("End", rows[0])

    def test_audit_block_matches_check_task(self):
        rows, audit = parse_uploaded_daily_csv(CSV_BYTES, self.filename, now=self.now)
        self.assertEqual(audit["check_count"], 1)
        self.assertEqual(rows[0]["_audit_detail"]["ผลตรวจสอบ"], "ข้อมูลจาก NAS ต้องได้รับการตรวจสอบ")

    def test_wrong_filename_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "ชื่อไฟล์"):
            parse_uploaded_daily_csv(CSV_BYTES, "latest.csv", now=self.now)

    def test_schema_change_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "รูปแบบ CSV"):
            parse_uploaded_daily_csv(CSV_BYTES.replace(b"Last Backup", b"Start", 1), self.filename, now=self.now)

    def test_check_without_audit_block_fails_closed(self):
        main_only = CSV_BYTES.split(b"\nAUDIT\n", 1)[0] + b"\n"
        with self.assertRaisesRegex(ValueError, "AUDIT"):
            parse_uploaded_daily_csv(main_only, self.filename, now=self.now)


class ProductionBundleContractTests(unittest.TestCase):
    def test_primary_browser_module_does_not_use_nas_api(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "synology_web_capture.py").read_text(encoding="utf-8")
        self.assertNotIn("synology_api", source)
        self.assertNotIn("SynologyClient", source)

    def test_yard_api_is_scoped_to_drive_sharesync(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "yard_api.py").read_text(encoding="utf-8")
        self.assertIn("SYNO.SynologyDriveShareSync.Connection", source)
        self.assertIn("SYNO.SynologyDriveShareSync.Session", source)
        self.assertNotIn("ActiveBackup", source)
        self.assertNotIn("FileStation", source)
        self.assertNotIn('credentials_for("primary"', source)

    def test_linux_bundle_script_excludes_nas_api_modules(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "build_linux_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn('"synology_api.py"', script)
        self.assertIn('"yard_api.py"', script)
        self.assertNotIn('"api_collector.py"', script)
        self.assertIn('"csv_report.py"', script)
        self.assertIn('"synology_web_capture.py"', script)

    def test_upgrade_removes_only_obsolete_collector(self):
        root = Path(__file__).resolve().parents[1]
        installer = (root / "deploy" / "linux" / "install.sh").read_text(encoding="utf-8")
        self.assertNotIn("rm -f /opt/backup-report/app/synology_api.py", installer)
        self.assertIn("/opt/backup-report/app/api_collector.py", installer)


if __name__ == "__main__":
    unittest.main()
