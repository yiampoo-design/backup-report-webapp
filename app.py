from __future__ import annotations

import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from http.cookies import SimpleCookie

from build_backup_report import build_pdf
from api_collector import collect_active_backup, collect_cloud_sync
from credential_store import protect_text, unprotect_text
from auth_store import AuthStore
from sangfor_capture import SangforCaptureError, capture_sangfor
from synology_api import SynologyApiError, SynologyClient, probe_read_only


APP_NAME = "Pylon Backup Report"
APP_VERSION = "0.7.8-all-abb-tasks"
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
    "version": 3,
    "primary": {
        "label": "NAS เครื่องหลัก - Active Backup",
        "url": "https://nas-primary.example.local:5001",
        "username": "",
        "password_encrypted": "",
        "verify_ssl": True,
        "profile": "active_backup",
    },
    "remote": {
        "label": "Yard - Cloud Sync",
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
    config, password = credentials_for(section, submitted)
    client = SynologyClient(
        config["url"], verify_ssl=bool(config.get("verify_ssl", True))
    )
    expected = (
        ["SYNO.ActiveBackup.Task", "SYNO.ActiveBackup.Log", "SYNO.ActiveBackup.Report"]
        if config["profile"] == "active_backup"
        else ["SYNO.CloudSync", "SYNO.LogCenter.Log"]
    )
    try:
        client.login(config["username"], password)
        discovered = client.discover(expected)
        return {
            "ok": True,
            "label": config["label"],
            "url": config["url"],
            "available_apis": sorted(discovered),
            "security_warning": config["url"].lower().startswith("http://"),
        }
    finally:
        client.logout()


SENSITIVE_PARTS = (
    "pass",
    "token",
    "secret",
    "access_key",
    "auth_key",
    "sid",
    "cookie",
)


def sanitize(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(part in key.lower() for part in SENSITIVE_PARTS)
            else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def probe_site(section: str, submitted: dict | None = None) -> dict:
    config, password = credentials_for(section, submitted)
    client = SynologyClient(
        config["url"], verify_ssl=bool(config.get("verify_ssl", True))
    )
    try:
        client.login(config["username"], password)
        result = probe_read_only(client, config["profile"])
    finally:
        client.logout()
    safe = sanitize(result)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = LOG_ROOT / f"api_probe_{section}_{stamp}.json"
    output.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    successes = [item for item in safe["calls"] if item.get("success")]
    return {
        "ok": True,
        "file": str(output),
        "successful_calls": [f"{item['api']}.{item['method']}" for item in successes],
        "attempted_calls": len(safe["calls"]),
    }


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


def generate_report(payload: dict) -> dict:
    save_settings(payload)
    report_settings = load_settings()["report"]
    primary_config, primary_password = credentials_for("primary", payload.get("primary"))
    remote_config, remote_password = credentials_for("remote", payload.get("remote"))
    primary = SynologyClient(primary_config["url"], verify_ssl=bool(primary_config.get("verify_ssl", True)), timeout=30)
    remote = SynologyClient(remote_config["url"], verify_ssl=bool(remote_config.get("verify_ssl", True)), timeout=30)
    try:
        primary.login(primary_config["username"], primary_password)
        rows, audit = collect_active_backup(
            primary,
            int(report_settings.get("alert_days", 7)),
            int(report_settings.get("report_hour", 9)),
        )
        remote.login(remote_config["username"], remote_password)
        audit["cloud_sync"] = collect_cloud_sync(remote)
        audit["cloud_sync"]["site_label"] = str(remote_config.get("label") or "Yard - Cloud Sync")
    finally:
        primary.logout()
        remote.logout()
        primary_password = remote_password = ""
    audit.update({
        "result_sha": "direct-api", "raw_sha": "direct-api",
        "result_path": Path("Active Backup Web API"), "raw_path": Path("Cloud Sync Web API"),
    })
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
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
    )
    return {
        "ok": True, "name": output.name, "path": str(output),
        "url": f"/api/report/{quote(output.name)}", "rows": len(rows),
        "check_count": sum(1 for row in rows if row["Audit Status"] == "Check"),
        "missing_task_count": audit["missing_task_count"],
        "data_cutoff": audit["data_cutoff"].isoformat(),
        "latest_result_time": audit["latest_result_time"].isoformat() if audit["latest_result_time"] else None,
        "is_final_window": audit["is_final_window"],
        "cloud_sync": audit["cloud_sync"], "sangfor": sangfor_result,
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
            cutoff_date = (datetime.now() - timedelta(days=6)).date()
            reports = [
                {
                    "name": item.name,
                    "size": item.stat().st_size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                }
                for item in sorted(REPORT_ROOT.glob("*.pdf"), reverse=True)
                if datetime.fromtimestamp(item.stat().st_mtime).date() >= cutoff_date
            ]
            return self._json({"ok": True, "days": 7, "reports": reports})
        if path.startswith("/api/report/"):
            filename = Path(unquote(path.removeprefix("/api/report/"))).name
            download = parse_qs(parsed.query).get("download", [""])[0] == "1"
            return self._serve_file(REPORT_ROOT / filename, "application/pdf", attachment=download)
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
            if parsed.path == "/api/probe":
                section = payload.get("section")
                if section not in ("primary", "remote"):
                    raise ValueError("Unknown NAS section")
                return self._json(probe_site(section, payload.get(section)))
            if parsed.path == "/api/test-sangfor":
                return self._json(test_sangfor(payload.get("sangfor")))
            if parsed.path == "/api/generate":
                return self._json(generate_report(payload))
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
        except (ValueError, SynologyApiError, SangforCaptureError, OSError, json.JSONDecodeError) as exc:
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
