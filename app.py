from __future__ import annotations

import json
import hashlib
import base64
import binascii
import mimetypes
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import webbrowser
from io import BytesIO
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from http.cookies import SimpleCookie

from build_backup_report import build_pdf
from csv_report import ACTIVE_BACKUP_DAILY_COLUMNS, BANGKOK, parse_uploaded_daily_csv
from credential_store import protect_text, unprotect_text
from auth_store import AuthStore
from sangfor_capture import SangforCaptureError, capture_sangfor
from synology_web_capture import (
    SynologyWebCaptureError,
    download_daily_csv,
)
from yard_api import collect_drive_sharesync
from PIL import Image as PILImage, UnidentifiedImageError


APP_NAME = "Pylon Backup Report"
APP_VERSION = "0.14.3-task-list-order"
SOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PORTABLE_ROOT = Path(os.environ.get("BACKUP_REPORT_ROOT", "")) if os.environ.get("BACKUP_REPORT_ROOT") else (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
STATIC_ROOT = SOURCE_ROOT / "web"
DATA_ROOT = Path(os.environ.get("BACKUP_REPORT_DATA_ROOT", str(PORTABLE_ROOT / "data")))
REPORT_ROOT = Path(os.environ.get("BACKUP_REPORT_REPORT_ROOT", str(PORTABLE_ROOT / "reports")))
LOG_ROOT = Path(os.environ.get("BACKUP_REPORT_LOG_ROOT", str(PORTABLE_ROOT / "logs")))
CAPTURE_ROOT = Path(os.environ.get("BACKUP_REPORT_CAPTURE_ROOT", str(PORTABLE_ROOT / "captures")))
SETTINGS_PATH = DATA_ROOT / "settings.json"
AUTH_PATH = DATA_ROOT / "web_auth.json"
WEB_USERNAME = os.environ.get("BACKUP_REPORT_WEB_USERNAME", "")
WEB_PASSWORD = os.environ.get("BACKUP_REPORT_WEB_PASSWORD", "")
SESSION_TTL_SECONDS = int(os.environ.get("BACKUP_REPORT_SESSION_HOURS", "12")) * 3600
COOKIE_SECURE = os.environ.get("BACKUP_REPORT_COOKIE_SECURE", "0") == "1"
AUTH_STORE = AuthStore(AUTH_PATH)
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()


DEFAULT_SETTINGS = {
    "version": 5,
    "primary": {
        "label": "NAS เครื่องหลัก - Active Backup",
        "url": "https://nas-primary.example.local:5001",
        "username": "",
        "password_encrypted": "",
        "verify_ssl": True,
        "profile": "active_backup",
    },
    "remote": {
        "label": "Yard - Drive ShareSync",
        "url": "https://nas-secondary.example.local:5001",
        "username": "",
        "password_encrypted": "",
        "verify_ssl": True,
        "profile": "cloud_sync",
    },
    "sangfor": {
        "label": "Sangfor aCloud - VM Backup",
        "url": "https://acloud.example.local",
        "username": "",
        "password_encrypted": "",
        "verify_ssl": False,
        "enabled": True,
        "backup_path": "/#/mod-setting/vm-backup/index?tab=recover",
    },
    "report": {
        "server_name": "BACKUP-SERVER",
        "alert_days": 7,
        "report_hour": 9,
    },
}


def ensure_directories() -> None:
    for path in (DATA_ROOT, REPORT_ROOT, LOG_ROOT, CAPTURE_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def deep_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def load_settings() -> dict:
    ensure_directories()
    settings = deep_copy(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        for section in ("primary", "remote", "sangfor", "report"):
            submitted = loaded.get(section, {})
            for key in settings[section]:
                if key in submitted:
                    settings[section][key] = submitted[key]
        if int(loaded.get("version", 1) or 1) < 2 and int(settings["report"].get("alert_days", 3) or 3) == 3:
            settings["report"]["alert_days"] = 7
        if int(loaded.get("version", 1) or 1) < 4:
            old_label = str(settings["remote"].get("label") or "")
            if "Cloud Sync" in old_label:
                settings["remote"]["label"] = old_label.replace("Cloud Sync", "Drive ShareSync")
    return settings


def save_settings(payload: dict) -> dict:
    current = load_settings()
    for section in ("primary", "remote", "sangfor"):
        submitted = payload.get(section, {})
        for key in ("label", "url", "username", "verify_ssl", "enabled", "backup_path"):
            if key in submitted:
                current[section][key] = submitted[key]
        password = submitted.get("password")
        if password:
            current[section]["password_encrypted"] = protect_text(str(password))
        elif submitted.get("forget_password"):
            current[section]["password_encrypted"] = ""
    submitted_report = payload.get("report", {})
    for key in ("server_name", "alert_days", "report_hour"):
        if key in submitted_report:
            current["report"][key] = submitted_report[key]

    temp = SETTINGS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(SETTINGS_PATH)
    return public_settings(current)


def public_settings(settings: dict) -> dict:
    result = deep_copy(settings)
    for section in ("primary", "remote", "sangfor"):
        encrypted = result[section].pop("password_encrypted", "")
        result[section]["password_saved"] = bool(encrypted)
    result["app"] = {
        "name": APP_NAME,
        "version": APP_VERSION,
        "portable_root": str(PORTABLE_ROOT),
        "report_root": str(REPORT_ROOT),
    }
    return result


def record_source_contract_alert(message: str, csv_path: str) -> Path:
    """Persist a non-secret, de-duplicated source-contract warning."""
    ensure_directories()
    observed_at = datetime.now().astimezone()
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]
    expected_schema_fingerprint = hashlib.sha256(
        ",".join(ACTIVE_BACKUP_DAILY_COLUMNS).encode("utf-8")
    ).hexdigest()
    output = LOG_ROOT / f"source_contract_{observed_at:%Y-%m-%d}_{digest}.json"
    output.write_text(json.dumps({
        "type": "active_backup_source_contract",
        "observed_at": observed_at.isoformat(),
        "configured_path": csv_path,
        "message": message,
        "observed_fingerprint": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "expected_schema_fingerprint": expected_schema_fingerprint,
        "action": "final_report_blocked",
        "nas_modified": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def list_recent_source_alerts(days: int = 7) -> list[dict[str, str]]:
    cutoff_date = (datetime.now() - timedelta(days=days - 1)).date()
    alerts: list[dict[str, str]] = []
    for item in sorted(LOG_ROOT.glob("source_contract_*.json"), reverse=True):
        try:
            payload = json.loads(item.read_text(encoding="utf-8"))
            observed = datetime.fromisoformat(str(payload["observed_at"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        if observed.date() < cutoff_date:
            continue
        alerts.append({
            "observed_at": observed.isoformat(),
            "message": str(payload.get("message") or "-"),
            "action": str(payload.get("action") or "final_report_blocked"),
        })
    return alerts


def credentials_for(section: str, submitted: dict | None = None) -> tuple[dict, str]:
    settings = load_settings()
    config = settings[section]
    submitted = submitted or {}
    username = str(submitted.get("username") or config.get("username") or "")
    password = str(submitted.get("password") or "")
    if not password and config.get("password_encrypted"):
        password = unprotect_text(config["password_encrypted"])
    if not username or not password:
        raise ValueError(f"กรุณากรอก Username และ Password สำหรับ {config['label']}")
    merged = dict(config)
    merged.update({key: value for key, value in submitted.items() if value not in (None, "")})
    return merged, password


def test_site(section: str, submitted: dict | None = None) -> dict:
    """Test the production data path for the selected site."""
    config, password = credentials_for(section, submitted)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = CAPTURE_ROOT / f"test_{section}_{stamp}"
    try:
        if section == "primary":
            report_date = datetime.now(BANGKOK).date()
            result = download_daily_csv(config, password, report_date, output_dir)
            rows, audit = parse_uploaded_daily_csv(
                bytes(result["content"]), str(result["name"])
            )
            return {
                "ok": True,
                "capture_method": "primary_csv_via_file_station",
                "filename": result["name"],
                "row_count": len(rows),
                "check_count": audit["check_count"],
            }
        elif section == "remote":
            result = collect_drive_sharesync(config, password)
            return {
                "ok": True,
                "capture_method": "yard_drive_sharesync_web_api",
                "connection_count": int(result.get("connection_count") or 0),
                "up_to_date_count": int(result.get("up_to_date_count") or 0),
                "api_methods": result.get("api_methods") or [],
            }
        else:
            raise ValueError("Unknown DSM section")
    finally:
        password = ""


def test_sangfor(submitted: dict | None = None) -> dict:
    config, password = credentials_for("sangfor", submitted)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = CAPTURE_ROOT / f"sangfor_test_{stamp}.png"
    try:
        result = capture_sangfor(config, password, output)
    finally:
        password = ""
    result["name"] = output.name
    result["preview_url"] = f"/api/capture/{quote(output.name)}"
    return result


def smoke_test_daily_csv(submitted: dict | None = None) -> dict:
    """Live DSM smoke: download and parse today's CSV without generating a PDF."""
    config, password = credentials_for("primary", submitted)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = CAPTURE_ROOT / f"smoke_csv_{stamp}"
    try:
        downloaded = download_daily_csv(
            config, password, datetime.now(BANGKOK).date(), output_dir
        )
        rows, audit = parse_uploaded_daily_csv(
            bytes(downloaded["content"]),
            str(downloaded["name"]),
            int(load_settings()["report"].get("report_hour", 9)),
        )
    finally:
        password = ""
    return {
        "ok": True,
        "name": downloaded["name"],
        "path": downloaded["path"],
        "size": len(downloaded["content"]),
        "sha256": audit["result_sha"],
        "rows": len(rows),
        "check_count": audit["check_count"],
        "source_type": downloaded["source_type"],
    }


def build_daily_message(rows: list[dict[str, str]], audit: dict, sangfor_result: dict) -> str:
    report_date = audit["report_date"]
    buddhist_year = report_date.year + 543
    date_text = f"{report_date:%d/%m}/{buddhist_year}"

    file_rows = [row for row in rows if str(row.get("Group", "")).casefold() == "file backup"]
    file_success = sum(1 for row in file_rows if row.get("Status") == "Successful")
    if file_rows and file_success == len(file_rows):
        file_status = "All successful"
    elif file_rows:
        file_status = f"{file_success}/{len(file_rows)} successful"
    else:
        file_status = "ไม่พบรายการ File Backup"

    cloud = audit.get("cloud_sync") or {}
    connection_count = int(cloud.get("connection_count") or 0)
    up_to_date_count = int(cloud.get("up_to_date_count") or 0)
    if connection_count and up_to_date_count == connection_count:
        yard_status = "All Up-to-Date"
    elif connection_count:
        yard_status = f"{up_to_date_count}/{connection_count} Up-to-Date"
    else:
        yard_status = "ไม่พบรายการ Synced folders"

    if sangfor_result.get("enabled") and sangfor_result.get("sort_verified"):
        hci_status = "ตรวจสอบหน้า HCI Backup สำเร็จ"
    elif sangfor_result.get("enabled"):
        hci_status = "แนบภาพ HCI Backup แล้ว แต่ยังไม่ยืนยันลำดับ Latest Backup"
    else:
        hci_status = "ไม่ได้แนบข้อมูล HCI Backup"

    check_rows = [
        row for row in rows
        if row.get("Audit Status") == "Check" or row.get("Status") != "Successful"
    ]
    lines = [
        f"Backup daily report วันที่ {date_text}",
        "รายละเอียดตามลิงค์ครับ",
        f"Task File Backup:  {file_status}",
        f"Backup to Cloud (Yard) Status : {yard_status}",
        f"HCI Backup  : {hci_status}",
    ]
    if not check_rows:
        lines.append("หมายเหตุ : ไม่พบ Task ที่ต้องตรวจสอบ")
        return "\n".join(lines)

    same_size_days = []
    for row in check_rows:
        value = str(row.get("Same Size") or "").strip()
        if value.isdigit() and int(value) > 0:
            same_size_days.append(int(value))
    if same_size_days and len(same_size_days) == len(check_rows) and len(set(same_size_days)) == 1:
        lines.append(
            f"หมายเหตุ : มี {len(check_rows)} Task ขนาดไฟล์ Backup เท่าเดิม {same_size_days[0]} วัน"
        )
    else:
        lines.append(f"หมายเหตุ : มี {len(check_rows)} Task ที่ต้องตรวจสอบ")

    for row in check_rows:
        audit_detail = row.get("_audit_detail") or {}
        authoritative_finding = str(audit_detail.get("ผลตรวจสอบ") or "").strip()
        if authoritative_finding:
            finding = authoritative_finding
        elif row.get("Status") == "Successful" and str(row.get("Size") or "").strip() in {
            "0 Bytes", "0 KB", "0.00 KB", "0 MB", "0.00 MB",
        }:
            finding = "Backup สำเร็จไม่มีไฟล์ใหม่"
        elif row.get("Status") == "Successful" and row.get("Audit Status") == "Check":
            finding = "Backup สำเร็จ แต่ขนาดหรือจำนวนไฟล์เท่าเดิมตามเกณฑ์"
        else:
            finding = str(row.get("Note") or "โปรดตรวจสอบผลการ Backup")
        lines.append(
            f"{row.get('No.', '-')} {row.get('Group', '-')} {row.get('Backup Task', '-')} "
            f"Backup {row.get('Status', '-')} {finding}"
        )
    return "\n".join(lines)


def list_recent_reports(report_root: Path, days: int = 7) -> list[dict[str, object]]:
    cutoff_date = (datetime.now() - timedelta(days=days - 1)).date()
    reports = []
    for item in sorted(report_root.glob("*.pdf"), reverse=True):
        modified = datetime.fromtimestamp(item.stat().st_mtime)
        if modified.date() < cutoff_date:
            continue
        summary_path = item.with_suffix(".txt")
        reports.append({
            "name": item.name,
            "size": item.stat().st_size,
            "modified": modified.isoformat(),
            "summary_available": summary_path.is_file(),
            "summary": summary_path.read_text(encoding="utf-8").strip() if summary_path.is_file() else "",
        })
    return reports


def delete_report_files(report_root: Path, filename: str) -> list[str]:
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.casefold() != ".pdf":
        raise ValueError("ชื่อไฟล์รายงานไม่ถูกต้อง")
    pdf_path = report_root / safe_name
    if not pdf_path.is_file():
        raise ValueError("ไม่พบไฟล์รายงานที่ต้องการลบ")
    removed = []
    for target in (pdf_path, pdf_path.with_suffix(".txt")):
        if target.is_file():
            target.unlink()
            removed.append(target.name)
    return removed


def cleanup_old_reports(report_root: Path, days: int = 7) -> list[str]:
    cutoff_date = (datetime.now() - timedelta(days=days - 1)).date()
    removed = []
    for pdf_path in sorted(report_root.glob("*.pdf")):
        modified_date = datetime.fromtimestamp(pdf_path.stat().st_mtime).date()
        if modified_date < cutoff_date:
            removed.extend(delete_report_files(report_root, pdf_path.name))
    return removed


def resolve_active_backup_csv(
    payload: dict,
    primary_config: dict,
    primary_password: str,
    capture_dir: Path,
    report_date=None,
) -> tuple[str, bytes, str]:
    """Use an optional manual CSV, otherwise download today's exact file via DSM UI."""
    upload = payload.get("active_backup_csv") or {}
    filename = Path(str(upload.get("name") or "")).name
    encoded = str(upload.get("content_base64") or "")
    if filename and encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("ข้อมูลไฟล์ CSV ที่อัปโหลดไม่ถูกต้อง") from exc
        return filename, content, "manual_upload"
    if filename or encoded:
        raise ValueError("ข้อมูลไฟล์ CSV ที่อัปโหลดไม่ครบถ้วน")

    downloaded = download_daily_csv(
        primary_config,
        primary_password,
        report_date or datetime.now(BANGKOK).date(),
        capture_dir / "file_station",
    )
    return (
        str(downloaded["name"]),
        bytes(downloaded["content"]),
        str(downloaded["source_type"]),
    )


def resolve_task_list_image(payload: dict, capture_dir: Path) -> Path | None:
    """Validate and persist an optional operator-supplied Task List screenshot."""
    upload = payload.get("task_list_image") or {}
    filename = Path(str(upload.get("name") or "")).name
    encoded = str(upload.get("content_base64") or "")
    if not filename and not encoded:
        return None
    if not filename or not encoded:
        raise ValueError("ข้อมูลภาพ Task List ที่อัปโหลดไม่ครบถ้วน")
    if Path(filename).suffix.casefold() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("ภาพ Task List ต้องเป็นไฟล์ PNG หรือ JPEG เท่านั้น")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("ข้อมูลภาพ Task List ที่อัปโหลดไม่ถูกต้อง") from exc
    if not content or len(content) > 12 * 1024 * 1024:
        raise ValueError("ภาพ Task List ต้องมีขนาดไม่เกิน 12 MB")
    try:
        with PILImage.open(BytesIO(content)) as image:
            image.verify()
        with PILImage.open(BytesIO(content)) as image:
            width, height = image.size
            image_format = str(image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("ไฟล์ที่เลือกไม่ใช่ภาพ PNG หรือ JPEG ที่สมบูรณ์") from exc
    if image_format not in {"PNG", "JPEG"}:
        raise ValueError("ภาพ Task List ต้องเป็นไฟล์ PNG หรือ JPEG เท่านั้น")
    if width < 320 or height < 180 or width * height > 60_000_000:
        raise ValueError("ขนาดพิกเซลของภาพ Task List ไม่เหมาะสม")
    destination = capture_dir / f"task-list{'.png' if image_format == 'PNG' else '.jpg'}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def generate_report(payload: dict) -> dict:
    save_settings(payload)
    report_settings = load_settings()["report"]
    primary_config, primary_password = credentials_for("primary", payload.get("primary"))
    remote_config, remote_password = credentials_for("remote", payload.get("remote"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = CAPTURE_ROOT / f"report_{stamp}"
    task_list_image_path = resolve_task_list_image(payload, capture_dir)
    filename, csv_content, source_mode = resolve_active_backup_csv(
        payload, primary_config, primary_password, capture_dir
    )
    try:
        rows, audit = parse_uploaded_daily_csv(
            csv_content,
            filename,
            int(report_settings.get("report_hour", 9)),
        )
        audit["source_type"] = source_mode
    except ValueError as exc:
        alert_path = record_source_contract_alert(str(exc), filename)
        raise ValueError(f"{exc} | บันทึกการแจ้งเตือน: {alert_path}") from exc

    try:
        yard_data = collect_drive_sharesync(remote_config, remote_password)
    finally:
        primary_password = remote_password = ""
    audit["cloud_sync"] = yard_data
    sangfor_capture_path = None
    sangfor_result = {"enabled": False}
    sangfor_settings = load_settings()["sangfor"]
    if bool(sangfor_settings.get("enabled", True)):
        sangfor_config, sangfor_password = credentials_for("sangfor", payload.get("sangfor"))
        sangfor_capture_path = CAPTURE_ROOT / f"sangfor_backup_{stamp}.png"
        try:
            sangfor_result = capture_sangfor(sangfor_config, sangfor_password, sangfor_capture_path)
            sangfor_result["enabled"] = True
        finally:
            sangfor_password = ""
    audit["sangfor_capture"] = sangfor_result
    output = REPORT_ROOT / f"Backup_Report_{audit['report_date'].isoformat()}_{stamp}.pdf"
    build_pdf(
        output,
        rows,
        audit,
        server_name=str(report_settings.get("server_name") or "BACKUP-SERVER"),
        sangfor_capture_path=sangfor_capture_path,
        task_list_image_path=task_list_image_path,
    )
    daily_summary = build_daily_message(rows, audit, sangfor_result)
    summary_output = output.with_suffix(".txt")
    summary_output.write_text(daily_summary + "\n", encoding="utf-8")
    return {
        "ok": True, "name": output.name, "path": str(output),
        "url": f"/api/report/{quote(output.name)}", "rows": len(rows),
        "check_count": sum(1 for row in rows if row["Audit Status"] == "Check"),
        "missing_task_count": audit["missing_task_count"],
        "data_cutoff": audit["data_cutoff"].isoformat(),
        "latest_result_time": audit["latest_result_time"].isoformat() if audit["latest_result_time"] else None,
        "is_final_window": audit["is_final_window"],
        "active_backup_source": audit["result_path"],
        "active_backup_source_mode": source_mode,
        "used_dated_fallback": audit["used_dated_fallback"],
        "capture_method": "Primary NAS CSV via DSM File Station",
        "task_list_image_attached": task_list_image_path is not None,
        "yard_capture": None,
        "sangfor": sangfor_result,
        "daily_summary": daily_summary,
        "summary_name": summary_output.name,
        "summary_path": str(summary_output),
        "summary_url": f"/api/report/{quote(summary_output.name)}",
    }


def find_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("ไม่พบ Local Port ที่ว่างสำหรับเปิดโปรแกรม")


class AppHandler(BaseHTTPRequestHandler):
    server_version = "PylonBackupReport"

    def log_message(self, fmt, *args):
        return

    @property
    def app_token(self) -> str:
        return self.server.app_token  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        if WEB_USERNAME:
            try:
                cookies = SimpleCookie(self.headers.get("Cookie", ""))
                session_id = cookies["backup_report_session"].value
            except (KeyError, AttributeError):
                return False
            now = time.time()
            with SESSIONS_LOCK:
                session = SESSIONS.get(session_id)
                if not session or float(session.get("expires", 0)) <= now:
                    SESSIONS.pop(session_id, None)
                    return False
                session["expires"] = now + SESSION_TTL_SECONDS
                self.current_session = session
                self.current_session_id = session_id
            return True
        parsed = urlparse(self.path)
        query_token = parse_qs(parsed.query).get("token", [""])[0]
        return secrets.compare_digest(
            self.headers.get("X-App-Token", "") or query_token,
            self.app_token,
        )

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _set_session_cookie(self, session_id: str):
        secure = "; Secure" if COOKIE_SECURE else ""
        self.send_header(
            "Set-Cookie",
            f"backup_report_session={session_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}{secure}",
        )

    def _clear_session_cookie(self):
        secure = "; Secure" if COOKIE_SECURE else ""
        self.send_header(
            "Set-Cookie",
            f"backup_report_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}",
        )

    def _csrf_valid(self) -> bool:
        if not WEB_USERNAME:
            return True
        session = getattr(self, "current_session", {})
        supplied = self.headers.get("X-CSRF-Token", "")
        expected = str(session.get("csrf") or "")
        return bool(supplied and expected and secrets.compare_digest(supplied, expected))

    def _error(self, exc: Exception, status: int = 400):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        error_log = LOG_ROOT / f"error_{stamp}.log"
        error_log.write_text(traceback.format_exc(), encoding="utf-8")
        self._json({"ok": False, "error": str(exc), "log": str(error_log)}, status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Request มีขนาดใหญ่เกินกำหนด")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            return self._json({"ok": True, "version": APP_VERSION})
        if path.startswith("/static/"):
            filename = Path(unquote(path.removeprefix("/static/"))).name
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return self._serve_file(STATIC_ROOT / filename, mime)
        if WEB_USERNAME and path == "/login":
            if self._authorized():
                return self._redirect("/")
            return self._serve_file(STATIC_ROOT / "login.html", "text/html; charset=utf-8")
        if WEB_USERNAME and not self._authorized():
            if path.startswith("/api/"):
                return self._json({"ok": False, "error": "กรุณาเข้าสู่ระบบ", "login_required": True}, 401)
            return self._redirect("/login")
        if path == "/":
            return self._serve_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
        if path.startswith("/api/") and not self._authorized():
            return self._json({"ok": False, "error": "Unauthorized local request"}, 403)
        if path == "/api/session":
            session = getattr(self, "current_session", {})
            return self._json({"ok": True, "username": AUTH_STORE.username(), "csrf_token": session.get("csrf", "")})
        if path == "/api/settings":
            return self._json({"ok": True, "settings": public_settings(load_settings())})
        if path == "/api/reports":
            reports = list_recent_reports(REPORT_ROOT, days=7)
            alerts = list_recent_source_alerts(days=7)
            return self._json({"ok": True, "days": 7, "reports": reports, "source_alerts": alerts})
        if path.startswith("/api/report/"):
            filename = Path(unquote(path.removeprefix("/api/report/"))).name
            download = parse_qs(parsed.query).get("download", [""])[0] == "1"
            mime = "text/plain; charset=utf-8" if Path(filename).suffix.casefold() == ".txt" else "application/pdf"
            return self._serve_file(REPORT_ROOT / filename, mime, attachment=download)
        if path.startswith("/api/capture/"):
            filename = Path(unquote(path.removeprefix("/api/capture/"))).name
            return self._serve_file(CAPTURE_ROOT / filename, "image/png")
        return self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_file(self, path: Path, mime: str, attachment: bool = False):
        if not path.exists() or not path.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if WEB_USERNAME and parsed.path == "/api/login":
            try:
                payload = self._read_json()
                username = str(payload.get("username") or "")
                password = str(payload.get("password") or "")
                if not AUTH_STORE.verify(username, password):
                    time.sleep(0.35)
                    return self._json({"ok": False, "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"}, 401)
                session_id = secrets.token_urlsafe(32)
                session = {
                    "username": username,
                    "csrf": secrets.token_urlsafe(24),
                    "expires": time.time() + SESSION_TTL_SECONDS,
                }
                with SESSIONS_LOCK:
                    SESSIONS[session_id] = session
                body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self._set_session_cookie(session_id)
                self.end_headers()
                return self.wfile.write(body)
            except (ValueError, json.JSONDecodeError) as exc:
                return self._error(exc)
        if not self._authorized():
            return self._json({"ok": False, "error": "กรุณาเข้าสู่ระบบ", "login_required": True}, 401)
        if not self._csrf_valid():
            return self._json({"ok": False, "error": "คำขอหมดอายุ กรุณาโหลดหน้าใหม่"}, 403)
        try:
            payload = self._read_json()
            if parsed.path == "/api/logout":
                with SESSIONS_LOCK:
                    SESSIONS.pop(getattr(self, "current_session_id", ""), None)
                body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self._clear_session_cookie()
                self.end_headers()
                return self.wfile.write(body)
            if parsed.path == "/api/change-password":
                current_password = str(payload.get("current_password") or "")
                new_password = str(payload.get("new_password") or "")
                confirm_password = str(payload.get("confirm_password") or "")
                username = AUTH_STORE.username()
                if not AUTH_STORE.verify(username, current_password):
                    raise ValueError("รหัสผ่านปัจจุบันไม่ถูกต้อง")
                if new_password != confirm_password:
                    raise ValueError("ยืนยันรหัสผ่านใหม่ไม่ตรงกัน")
                AUTH_STORE.set_password(username, new_password)
                with SESSIONS_LOCK:
                    SESSIONS.clear()
                body = json.dumps({"ok": True, "login_required": True}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self._clear_session_cookie()
                self.end_headers()
                return self.wfile.write(body)
            if parsed.path == "/api/settings":
                return self._json({"ok": True, "settings": save_settings(payload)})
            if parsed.path == "/api/test":
                sites = payload.get("sites", ["primary", "remote"])
                results = {}
                for section in sites:
                    try:
                        results[section] = test_site(section, payload.get(section))
                    except Exception as exc:
                        results[section] = {"ok": False, "error": str(exc)}
                return self._json({"ok": all(v["ok"] for v in results.values()), "results": results})
            if parsed.path == "/api/test-sangfor":
                return self._json(test_sangfor(payload.get("sangfor")))
            if parsed.path == "/api/smoke-csv":
                return self._json(smoke_test_daily_csv(payload.get("primary")))
            if parsed.path == "/api/generate":
                return self._json(generate_report(payload))
            if parsed.path == "/api/delete-report":
                removed = delete_report_files(REPORT_ROOT, str(payload.get("name") or ""))
                return self._json({"ok": True, "removed": removed})
            if parsed.path == "/api/cleanup-reports":
                removed = cleanup_old_reports(REPORT_ROOT, days=7)
                return self._json({"ok": True, "removed": removed, "file_count": len(removed)})
            if parsed.path == "/api/open-reports":
                if os.name == "nt":
                    os.startfile(REPORT_ROOT)
                    return self._json({"ok": True})
                return self._json({"ok": True, "history": True})
            if parsed.path == "/api/shutdown":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, SynologyWebCaptureError, SangforCaptureError, OSError, json.JSONDecodeError) as exc:
            return self._error(exc)
        except Exception as exc:
            return self._error(exc, 500)


def run() -> None:
    ensure_directories()
    if WEB_USERNAME:
        AUTH_STORE.initialize(WEB_USERNAME, WEB_PASSWORD)
    configured_port = os.environ.get("BACKUP_REPORT_PORT")
    port = int(configured_port) if configured_port else find_port()
    host = os.environ.get("BACKUP_REPORT_HOST", "127.0.0.1")
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer((host, port), AppHandler)
    server.app_token = token  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{port}/" + ("" if WEB_USERNAME else f"?token={quote(token)}")
    print(f"{APP_NAME} {APP_VERSION}")
    print(url)
    if os.environ.get("BACKUP_REPORT_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
