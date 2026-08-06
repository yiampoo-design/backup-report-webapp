from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_BACKUP_PATH = "/#/mod-setting/vm-backup/index?tab=recover"


class SangforCaptureError(RuntimeError):
    pass


def _root_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Sangfor URL ต้องขึ้นต้นด้วย http:// หรือ https://")
    return f"{parsed.scheme}://{parsed.netloc}"


def capture_sangfor(config: dict, password: str, output_path: Path) -> dict:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SangforCaptureError("Playwright is not installed on the report server") from exc

    browser_path = os.environ.get("BACKUP_REPORT_CHROMIUM", "/usr/bin/chromium-browser")
    if not Path(browser_path).is_file():
        raise SangforCaptureError(f"ไม่พบ Chromium: {browser_path}")

    root_url = _root_url(str(config.get("url") or ""))
    backup_path = str(config.get("backup_path") or DEFAULT_BACKUP_PATH)
    target_url = root_url + (backup_path if backup_path.startswith("/") else f"/{backup_path}")
    username = str(config.get("username") or "")
    if not username or not password:
        raise ValueError("กรุณากรอก Username และ Password สำหรับ Sangfor aCloud")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(os.environ.get("BACKUP_REPORT_CHROMIUM_RUNTIME", str(output_path.parent / "runtime")))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(runtime_dir, 0o700)

    browser = None
    context = None
    browser_env = dict(os.environ)
    browser_env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    browser_env["HOME"] = os.environ.get("HOME", str(output_path.parent))
    browser_env["XDG_RUNTIME_DIR"] = str(runtime_dir)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=browser_path,
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage"],
                env=browser_env,
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=not bool(config.get("verify_ssl", False)),
                locale="en-US",
            )
            page = context.new_page()
            page.set_default_timeout(45_000)
            page.goto(f"{root_url}/login", wait_until="domcontentloaded", timeout=60_000)

            username_input = page.get_by_placeholder("Username", exact=True)
            password_input = page.get_by_placeholder("Password", exact=True)
            username_input.wait_for(state="visible")
            username_input.fill(username)
            password_input.fill(password)

            consent = page.locator('input[type="checkbox"]')
            if consent.count() and not consent.first.is_checked():
                consent.first.check()

            page.get_by_role("button", name="Log In", exact=True).click()
            page.wait_for_timeout(4_000)
            page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(10_000)

            if "/login" in page.url or password_input.is_visible():
                raise SangforCaptureError("Sangfor login ไม่สำเร็จ กรุณาตรวจ Username และ Password")

            page.get_by_text("VM Name", exact=True).wait_for(state="visible", timeout=45_000)
            page.get_by_text("Latest Backup", exact=True).wait_for(state="visible", timeout=45_000)
            page.screenshot(path=str(output_path), full_page=False, type="png")
            context.close()
            browser.close()
            context = None
            browser = None
            return {
                "ok": True,
                "path": str(output_path),
                "url": target_url,
                "width": 1920,
                "height": 1080,
            }
    except PlaywrightTimeoutError as exc:
        raise SangforCaptureError("Sangfor โหลดหน้า Backup ไม่เสร็จภายในเวลาที่กำหนด") from exc
