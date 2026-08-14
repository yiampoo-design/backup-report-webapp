from __future__ import annotations

import os
import re
import time
from io import BytesIO
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageChops


class SynologyWebCaptureError(RuntimeError):
    pass


def _root_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("DSM URL ต้องขึ้นต้นด้วย http:// หรือ https://")
    return f"{parsed.scheme}://{parsed.netloc}"


def _runtime(output_dir: Path) -> tuple[str, Path, dict[str, str]]:
    browser_path = os.environ.get("BACKUP_REPORT_CHROMIUM", "/usr/bin/chromium-browser")
    if not Path(browser_path).is_file():
        raise SynologyWebCaptureError(f"ไม่พบ Chromium: {browser_path}")
    runtime_dir = Path(os.environ.get(
        "BACKUP_REPORT_CHROMIUM_RUNTIME",
        str(output_dir / "runtime"),
    ))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(runtime_dir, 0o700)
    browser_env = dict(os.environ)
    browser_env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    browser_env["HOME"] = os.environ.get("HOME", str(output_dir))
    browser_env["XDG_RUNTIME_DIR"] = str(runtime_dir)
    return browser_path, runtime_dir, browser_env


def _frames(page):
    return [page.main_frame, *[frame for frame in page.frames if frame is not page.main_frame]]


def _first_visible(locators):
    for locator in locators:
        try:
            count = locator.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    return None


def _text_locator(page, text: str, exact: bool = True, timeout_ms: int = 5_000):
    deadline = time.monotonic() + max(0, timeout_ms) / 1_000
    while True:
        for frame in _frames(page):
            locator = frame.get_by_text(text, exact=exact)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count - 1, -1, -1):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue
        if time.monotonic() >= deadline:
            break
        try:
            page.wait_for_timeout(200)
        except Exception:
            time.sleep(0.2)
    raise SynologyWebCaptureError(f"ไม่พบข้อความบนหน้า DSM: {text}")


def _visible_exact_text_count(page, text: str, scope=None) -> int:
    """Count visible exact text matches, optionally inside one DSM window."""
    if scope is not None:
        locator = scope.get_by_text(text, exact=True)
        visible = 0
        try:
            count = locator.count()
        except Exception:
            return 0
        for index in range(count):
            try:
                if locator.nth(index).is_visible():
                    visible += 1
            except Exception:
                continue
        return visible

    visible = 0
    for frame in _frames(page):
        locator = frame.get_by_text(text, exact=True)
        try:
            count = locator.count()
        except Exception:
            continue
        for index in range(count):
            try:
                if locator.nth(index).is_visible():
                    visible += 1
            except Exception:
                continue
    return visible


def _left_navigation_locator(page, text: str, max_x: float = 260, scope=None):
    """Return an exact visible DSM navigation item in the left sidebar.

    Active Backup's Overview repeats labels such as ``File Server`` in cards
    and status panels.  The sidebar is the only matching label whose bounding
    box is at the left edge of the fixed DSM viewport.
    """
    roots = [scope] if scope is not None else _frames(page)
    for root in roots:
        matches = root.get_by_text(text, exact=True)
        try:
            count = matches.count()
        except Exception:
            continue
        for index in range(count):
            candidate = matches.nth(index)
            try:
                if not candidate.is_visible():
                    continue
                box = candidate.bounding_box()
                if box and box["x"] < max_x:
                    return candidate
            except Exception:
                continue
    raise SynologyWebCaptureError(f"ไม่พบเมนูด้านซ้ายของ DSM: {text}")


def daily_csv_filename(report_date: date) -> str:
    return f"abb_daily_result_{report_date:%Y-%m-%d}.csv"


def require_exact_download_name(expected_name: str, suggested_name: str) -> None:
    observed = Path(suggested_name).name
    if observed.casefold() != expected_name.casefold():
        raise SynologyWebCaptureError(
            f"File Station ดาวน์โหลดชื่อไฟล์ไม่ตรง: expected={expected_name}; observed={observed}"
        )


def _body_text(page) -> str:
    values: list[str] = []
    for frame in _frames(page):
        try:
            values.append(frame.locator("body").inner_text(timeout=3_000))
        except Exception:
            continue
    return "\n".join(values)


def _active_backup_task_list_ready(page, app_window=None) -> bool:
    """Return True only when the visible Active Backup task grid is present.

    DSM builds do not expose the ``Task List`` tab consistently.  Some open
    the grid immediately after ``File Server`` is selected, while others keep
    the tab label in a hidden ExtJS template.  The grid column labels are the
    actual state we need, so they are the readiness contract.
    """
    required_headers = (
        "Task Name",
        "Backup mode",
        "Device",
        "Destination",
        "Last Backup",
        "Status",
    )
    return all(_visible_exact_text_count(page, header, app_window) > 0 for header in required_headers)


def _open_active_backup_task_list(page, output_dir: Path, app_window=None) -> None:
    """Reach the task grid without requiring the optional DSM tab label."""
    if _active_backup_task_list_ready(page, app_window):
        return

    if app_window is not None:
        task_list = _first_visible([app_window.get_by_text("Task List", exact=True)])
    else:
        try:
            task_list = _text_locator(page, "Task List", exact=True, timeout_ms=3_000)
        except SynologyWebCaptureError:
            task_list = None
    if task_list is not None:
        task_list.click(force=True)
        page.wait_for_timeout(3_000)

    if not _active_backup_task_list_ready(page, app_window):
        diagnostic = _save_diagnostic(page, output_dir, "active-backup-task-list-not-ready")
        raise SynologyWebCaptureError(
            f"หน้า Active Backup ยังไม่แสดงตาราง Task Name/Last Backup; "
            f"ดูภาพตรวจสอบที่ {diagnostic}"
        )


def _click_first_data_row(page) -> bool:
    for frame in _frames(page):
        for selector in ('tbody tr:visible', '[role="row"]:visible'):
            try:
                rows = frame.locator(selector)
                if rows.count():
                    row = rows.first
                    detail_control = _first_visible([
                        row.locator('button'),
                        row.locator('a'),
                        row.locator('[class*="detail" i]'),
                        row.locator('[title*="detail" i]'),
                    ])
                    if detail_control is not None:
                        detail_control.click(force=True)
                    else:
                        row.click(force=True)
                    return True
            except Exception:
                continue
    return False


def _task_grid_row(page, task_name: str, app_window=None):
    """Find the visible grid row that owns the exact task-name cell."""
    roots = [app_window] if app_window is not None else _frames(page)
    for root in roots:
        cells = root.get_by_text(task_name, exact=True)
        try:
            count = cells.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            cell = cells.nth(index)
            try:
                if not cell.is_visible():
                    continue
                for xpath in (
                    "xpath=ancestor::*[@role='row'][1]",
                    "xpath=ancestor::tr[1]",
                    "xpath=ancestor::*[contains(@class,'x-grid-row')][1]",
                    "xpath=ancestor::*[contains(@class,'x-grid-item')][1]",
                ):
                    row = cell.locator(xpath)
                    if row.count() and row.first.is_visible():
                        return row.first
            except Exception:
                continue
    raise SynologyWebCaptureError(f"ไม่พบแถว Task ในตาราง Active Backup: {task_name}")


def _active_backup_details_window(page, task_name: str):
    """Return the visible ``Details: <task>`` DSM window, if open."""
    title_pattern = re.compile(rf"^\s*Details\s*:\s*{re.escape(task_name)}\s*$", re.I)
    for frame in _frames(page):
        titles = frame.get_by_text(title_pattern)
        try:
            count = titles.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            title = titles.nth(index)
            try:
                if not title.is_visible():
                    continue
                for xpath in (
                    "xpath=ancestor::*[contains(@class,'x-window')][1]",
                    "xpath=ancestor::*[@role='dialog'][1]",
                ):
                    window = title.locator(xpath)
                    if window.count() and window.first.is_visible():
                        return window.first
            except Exception:
                continue
    return None


def _wait_for_active_backup_details(page, task_name: str, timeout_ms: int = 5_000):
    deadline = time.monotonic() + timeout_ms / 1_000
    while time.monotonic() < deadline:
        window = _active_backup_details_window(page, task_name)
        if window is not None:
            return window
        page.wait_for_timeout(200)
    return None


def _open_active_backup_details(page, task_name: str, output_dir: Path, app_window=None) -> None:
    """Select the real task row and open its Details view.

    Active Backup is an ExtJS application. Clicking only the text node does
    not consistently select the owning row, leaving the toolbar action
    disabled. Select the row container first, then use the visible enabled
    Details control. Double-clicking the same row is a DSM UI fallback.
    """
    row = _task_grid_row(page, task_name, app_window)
    _dismiss_taskbar_preview(page, output_dir)
    if not _locator_is_uncovered(row):
        diagnostic = _save_diagnostic(page, output_dir, "active-backup-task-row-covered")
        raise SynologyWebCaptureError(
            f"แถว Task {task_name} ยังถูกองค์ประกอบอื่นบัง; "
            f"ดูภาพตรวจสอบที่ {diagnostic}"
        )
    row.click(timeout=5_000)
    page.wait_for_timeout(800)

    root = app_window if app_window is not None else page
    details = _first_visible([
        root.get_by_role("button", name=re.compile(r"^Details$", re.I)),
        root.locator('[aria-label="Details" i]'),
        root.locator('[title="Details" i]'),
        root.get_by_text("Details", exact=True),
    ])
    if details is not None:
        try:
            enabled = details.is_enabled()
        except Exception:
            enabled = True
        if enabled:
            # A short timeout makes a foreground-window regression fail fast
            # instead of repeating the same intercepted click for 45 seconds.
            try:
                details.click(timeout=5_000)
            except Exception:
                _switch_active_backup_from_taskbar(page, output_dir)
                row = _task_grid_row(page, task_name, app_window)
                row.click(timeout=5_000)
                details = _first_visible([
                    root.get_by_role("button", name=re.compile(r"^Details$", re.I)),
                    root.locator('[aria-label="Details" i]'),
                    root.locator('[title="Details" i]'),
                    root.get_by_text("Details", exact=True),
                ])
                if details is None:
                    raise
                details.click(timeout=5_000)
            window = _wait_for_active_backup_details(page, task_name)
            if window is not None:
                return

    # DSM also opens Task Details by double-clicking a selected task row.
    _switch_active_backup_from_taskbar(page, output_dir)
    row = _task_grid_row(page, task_name, app_window)
    row.dblclick(timeout=5_000)
    window = _wait_for_active_backup_details(page, task_name)
    if window is not None:
        return

    diagnostic = _save_diagnostic(page, output_dir, "active-backup-details-not-open")
    raise SynologyWebCaptureError(
        f"เลือกแถว Task {task_name} แล้วแต่ไม่สามารถเปิด Details ได้; "
        f"ดูภาพตรวจสอบที่ {diagnostic}"
    )


def _open_active_backup_log(page, task_name: str, output_dir: Path) -> None:
    """Open Log inside the verified Details window for the selected task."""
    details_window = _active_backup_details_window(page, task_name)
    if details_window is None:
        diagnostic = _save_diagnostic(page, output_dir, "active-backup-details-window-missing")
        raise SynologyWebCaptureError(
            f"หน้าต่าง Details ของ Task {task_name} ไม่ได้เปิดอยู่; "
            f"ดูภาพตรวจสอบที่ {diagnostic}"
        )

    log_tab = _first_visible([
        details_window.get_by_role("tab", name=re.compile(r"^Log$", re.I)),
        details_window.get_by_text("Log", exact=True),
        details_window.locator('[aria-label="Log" i]'),
        details_window.locator('[title="Log" i]'),
    ])
    if log_tab is None:
        diagnostic = _save_diagnostic(page, output_dir, "active-backup-log-tab-not-found")
        raise SynologyWebCaptureError(
            f"พบหน้าต่าง Details ของ Task {task_name} แต่ไม่พบแท็บ Log ภายในหน้าต่าง; "
            f"ดูภาพตรวจสอบที่ {diagnostic}"
        )
    log_tab.click(force=True)
    page.wait_for_timeout(2_000)

    # The approved legacy evidence shows the Log grid with these columns.
    window_text = ""
    try:
        window_text = details_window.inner_text(timeout=3_000)
    except Exception:
        pass
    if not all(label in window_text for label in ("Type", "Time", "Event")):
        diagnostic = _save_diagnostic(page, output_dir, "active-backup-log-grid-not-ready")
        raise SynologyWebCaptureError(
            f"กดแท็บ Log ของ Task {task_name} แล้ว แต่ตาราง Type/Time/Event ยังไม่พร้อม; "
            f"ดูภาพตรวจสอบที่ {diagnostic}"
        )


def _save_diagnostic(page, output_dir: Path, name: str) -> Path:
    output = output_dir / f"diagnostic_{name}.png"
    try:
        page.screenshot(path=str(output), full_page=False, type="png")
    except Exception:
        pass
    return output


def _visual_change_ratio(before_png: bytes, after_png: bytes) -> float:
    """Return the fraction of pixels changed between two same-size captures."""
    with Image.open(BytesIO(before_png)) as before_image, Image.open(BytesIO(after_png)) as after_image:
        before = before_image.convert("RGB")
        after = after_image.convert("RGB")
        if before.size != after.size:
            raise SynologyWebCaptureError("ขนาดภาพก่อนและหลังเปิด Sync log ไม่ตรงกัน")
        difference = ImageChops.difference(before, after).convert("L")
        histogram = difference.histogram()
        changed_pixels = sum(histogram[1:])
        total_pixels = before.width * before.height
        return changed_pixels / total_pixels if total_pixels else 0.0


def _application_window(page, title_text: str):
    """Return the visible DSM application window containing its title."""
    for frame in _frames(page):
        titles = frame.get_by_text(title_text, exact=True)
        try:
            count = titles.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            title = titles.nth(index)
            try:
                if not title.is_visible():
                    continue
                for xpath in (
                    "xpath=ancestor::*[contains(@class,'x-window')][1]",
                    "xpath=ancestor::*[@role='dialog'][1]",
                ):
                    window = title.locator(xpath)
                    if window.count() and window.first.is_visible():
                        return window.first
            except Exception:
                continue
    raise SynologyWebCaptureError(f"ไม่พบกรอบหน้าต่าง DSM: {title_text}")


def _window_is_active(window) -> bool:
    try:
        classes = window.get_attribute("class") or ""
    except Exception:
        return False
    return "active-win" in classes.split()


def _locator_is_uncovered(locator) -> bool:
    """Return True only when the locator can actually receive a pointer event."""
    try:
        return bool(locator.evaluate(
            """
            (el) => {
              const rect = el.getBoundingClientRect();
              if (!rect.width || !rect.height) return false;
              const x = Math.max(0, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
              const y = Math.max(0, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
              const top = document.elementFromPoint(x, y);
              return !!top && (top === el || el.contains(top));
            }
            """
        ))
    except Exception:
        return False


def _dismiss_taskbar_preview(page, output_dir: Path) -> None:
    """Dismiss DSM's taskbar preview mask before interacting with app grids."""
    page.mouse.move(960, 540)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(500)

    for frame in _frames(page):
        masks = frame.locator(".preview-mask")
        try:
            count = masks.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            mask = masks.nth(index)
            try:
                if mask.is_visible():
                    mask.evaluate(
                        """el => el.dispatchEvent(new MouseEvent('click', {
                        bubbles: true, cancelable: true, view: window
                        }))"""
                    )
            except Exception:
                continue
    page.wait_for_timeout(500)

    for frame in _frames(page):
        masks = frame.locator(".preview-mask")
        try:
            if any(masks.nth(i).is_visible() for i in range(masks.count())):
                diagnostic = _save_diagnostic(page, output_dir, "taskbar-preview-mask-still-visible")
                raise SynologyWebCaptureError(
                    "DSM taskbar preview-mask ยังบังหน้าจอ; "
                    f"ดูภาพตรวจสอบที่ {diagnostic}"
                )
        except SynologyWebCaptureError:
            raise
        except Exception:
            continue


def _switch_active_backup_from_taskbar(page, output_dir: Path) -> None:
    """Switch apps through DSM's top taskbar, matching the real user action.

    On this DSM build the maximized application windows are DOM shells rather
    than registered Ext components, so ``toFront`` is unavailable.  The taskbar
    is fixed in the 1920x1080 capture viewport: main menu at x=70, Active Backup
    at x=135 and File Station at x=180.  Click the Active Backup task button and
    validate by its unique left navigation instead of relying on active-win.
    """
    # A locator can be Playwright-visible while covered by another maximized
    # DSM application. Only skip the switch when hit-testing proves the Active
    # Backup navigation can receive a real pointer event.
    try:
        navigation = _left_navigation_locator(page, "File Server")
        if _locator_is_uncovered(navigation):
            return
    except SynologyWebCaptureError:
        pass

    page.mouse.click(135, 25)
    page.wait_for_timeout(1_500)
    _dismiss_taskbar_preview(page, output_dir)
    try:
        navigation = _left_navigation_locator(page, "File Server")
        if _locator_is_uncovered(navigation):
            return
    except SynologyWebCaptureError:
        pass
    diagnostic = _save_diagnostic(page, output_dir, "active-backup-taskbar-switch-failed")
    raise SynologyWebCaptureError(
        "คลิกไอคอน Active Backup บนแถบงาน DSM แล้ว แต่เมนู File Server "
        "ยังถูกหน้าต่างอื่นบัง; "
        f"ดูภาพตรวจสอบที่ {diagnostic}"
    )


def _dismiss_restored_settings_dialog(page) -> bool:
    """Close a restored DSM Settings dialog without saving any changes."""
    for frame in _frames(page):
        titles = frame.get_by_text("Settings", exact=True)
        try:
            count = titles.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            title = titles.nth(index)
            try:
                if not title.is_visible():
                    continue
                dialog = None
                for xpath in (
                    "xpath=ancestor::*[contains(@class,'x-window')][1]",
                    "xpath=ancestor::*[@role='dialog'][1]",
                ):
                    candidate = title.locator(xpath)
                    if candidate.count() and candidate.first.is_visible():
                        dialog = candidate.first
                        break
                if dialog is None:
                    continue
                cancel = _first_visible([
                    dialog.get_by_role("button", name=re.compile(r"^Cancel$", re.I)),
                    dialog.get_by_text("Cancel", exact=True),
                    dialog.locator('.x-tool-close'),
                    dialog.locator('[aria-label*="Close" i]'),
                ])
                if cancel is None:
                    continue
                cancel.click()
                page.wait_for_timeout(800)
                return True
            except Exception:
                continue
    return False


def _active_file_station_window(page):
    """Return the foreground File Station window that can cover other DSM apps."""
    selectors = (
        "div.x-window.syno-sds-fs-win.active-win",
        "div.syno-sds-fs-win.active-win",
    )
    for frame in _frames(page):
        for selector in selectors:
            windows = frame.locator(selector)
            try:
                count = windows.count()
            except Exception:
                continue
            for index in range(count - 1, -1, -1):
                window = windows.nth(index)
                try:
                    if window.is_visible():
                        return window
                except Exception:
                    continue
    return None


def _invoke_ext_window_action(window, action: str) -> dict:
    """Invoke a DSM ExtJS window action without a pointer click.

    This is deliberately scoped to a previously verified application-window
    locator.  It cannot select toolbar controls from another DSM application.
    """
    return window.evaluate(
        """
        (el, action) => {
          const result = {ok: false, via: null, action: action, componentId: null};
          const componentId = el.getAttribute('syno-ext-id') || el.id || null;
          result.componentId = componentId;
          const ext = window.Ext;
          const component = ext && componentId && typeof ext.getCmp === 'function'
            ? ext.getCmp(componentId)
            : null;
          const methods = action === 'minimize'
            ? ['minimize', 'collapse']
            : action === 'close'
              ? ['close', 'hide']
              : ['toFront', 'bringToFront', 'show'];
          if (component) {
            for (const method of methods) {
              if (typeof component[method] === 'function') {
                component[method]();
                result.ok = true;
                result.via = `Ext.${method}`;
                return result;
              }
            }
          }

          const header = el.querySelector('.x-window-header, .x-window-tl') || el;
          const selector = action === 'minimize'
            ? '.x-tool-minimize, [aria-label*="Minimize" i], [title*="Minimize" i]'
            : action === 'close'
              ? '.x-tool-close, [aria-label*="Close" i], [title*="Close" i]'
              : null;
          const target = selector ? header.querySelector(selector) : header;
          if (!target) return result;
          for (const type of ['mousedown', 'mouseup', 'click']) {
            target.dispatchEvent(new MouseEvent(type, {
              bubbles: true, cancelable: true, view: window, button: 0
            }));
          }
          result.ok = true;
          result.via = selector ? 'DOM.titlebar-control' : 'DOM.window-header';
          return result;
        }
        """,
        action,
    )


def _remove_file_station_from_foreground(page, output_dir: Path) -> None:
    """Minimize a restored File Station window without changing NAS data.

    DSM restores the last maximized File Station window for the account.  That
    window may remain ``active-win`` even after Active Backup is opened and it
    then intercepts the Details click.  Cancel any child Settings dialog first,
    then use the File Station title-bar minimize control.  Closing the app
    window is a safe UI-only fallback when this DSM build has no minimize
    control.
    """
    attempts: list[str] = []
    for _ in range(2):
        for _dialog_attempt in range(3):
            if not _dismiss_restored_settings_dialog(page):
                break
        window = _active_file_station_window(page)
        if window is None:
            return

        for action in ("minimize", "close"):
            try:
                result = _invoke_ext_window_action(window, action)
                attempts.append(
                    f"{action}: ok={result.get('ok')} via={result.get('via')} "
                    f"component={result.get('componentId')}"
                )
            except Exception as exc:
                attempts.append(f"{action}: exception={type(exc).__name__}: {exc}")
            page.wait_for_timeout(800)
            if _active_file_station_window(page) is None:
                return

    if _active_file_station_window(page) is not None:
        diagnostic = _save_diagnostic(page, output_dir, "file-station-still-foreground")
        raise SynologyWebCaptureError(
            "File Station ยังอยู่ด้านหน้าและบัง Active Backup; "
            f"attempts=[{' | '.join(attempts)}]; ดูภาพตรวจสอบที่ {diagnostic}"
        )


def _activate_application_window(page, app_name: str, output_dir: Path):
    """Bring an existing DSM app window to front, then verify foreground state.

    A maximized File Station window has no minimize/close title-bar controls.
    The correct DSM operation is therefore to call ``toFront`` on Active
    Backup's ExtJS window.  Only open the application from the menu when no
    existing window is present.
    """
    for _ in range(3):
        if not _dismiss_restored_settings_dialog(page):
            break
    try:
        window = _application_window(page, app_name)
    except SynologyWebCaptureError:
        _open_application(page, app_name, output_dir)
        try:
            window = _application_window(page, app_name)
        except SynologyWebCaptureError as exc:
            diagnostic = _save_diagnostic(page, output_dir, "active-backup-window-not-found")
            raise SynologyWebCaptureError(
                f"เปิด {app_name} แล้วแต่ไม่พบกรอบหน้าต่างของแอป; "
                f"ดูภาพตรวจสอบที่ {diagnostic}"
            ) from exc
    if app_name == "Active Backup for Business":
        _switch_active_backup_from_taskbar(page, output_dir)
    else:
        title = _first_visible([window.get_by_text(app_name, exact=True)])
        if title is not None:
            title.click(timeout=5_000)
            page.wait_for_timeout(800)
    return window


def _login(page, root_url: str, username: str, password: str, output_dir: Path) -> None:
    if not username or not password:
        raise ValueError("กรุณากรอก Username และ Password สำหรับ DSM Web Capture")
    page.goto(root_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_500)

    username_input = _first_visible([
        page.locator('input[name="username"]'),
        page.locator('input[name="account"]'),
        page.locator('input[placeholder*="Username" i]'),
        page.locator('input[placeholder*="ชื่อผู้ใช้"]'),
        page.locator('input[type="text"]'),
    ])
    if username_input is None:
        # A fresh browser should normally show the login form. If the DSM
        # desktop is already visible, continue without submitting credentials.
        if "Control Panel" in _body_text(page) or "Package Center" in _body_text(page):
            return
        diagnostic = _save_diagnostic(page, output_dir, "login-form-not-found")
        raise SynologyWebCaptureError(f"ไม่พบช่อง Login DSM; ดูภาพตรวจสอบที่ {diagnostic}")
    username_input.fill(username)

    password_input = _first_visible([
        page.locator('input[name="password"]'),
        page.locator('input[placeholder*="Password" i]'),
        page.locator('input[placeholder*="รหัสผ่าน"]'),
        page.locator('input[type="password"]'),
    ])
    if password_input is None:
        # DSM can use a two-step login flow.
        next_button = _first_visible([
            page.get_by_role("button", name=re.compile(r"next|ถัดไป|sign in|login|เข้าสู่ระบบ", re.I)),
            page.locator('button[type="submit"]'),
        ])
        if next_button is None:
            diagnostic = _save_diagnostic(page, output_dir, "password-step-not-found")
            raise SynologyWebCaptureError(f"ไม่พบขั้นตอน Password DSM; ดูภาพตรวจสอบที่ {diagnostic}")
        next_button.click()
        page.wait_for_timeout(1_500)
        password_input = _first_visible([
            page.locator('input[name="password"]'),
            page.locator('input[placeholder*="Password" i]'),
            page.locator('input[type="password"]'),
        ])
    if password_input is None:
        diagnostic = _save_diagnostic(page, output_dir, "password-not-found")
        raise SynologyWebCaptureError(f"ไม่พบช่อง Password DSM; ดูภาพตรวจสอบที่ {diagnostic}")
    password_input.fill(password)
    login_button = _first_visible([
        page.get_by_role("button", name=re.compile(r"sign in|log in|login|เข้าสู่ระบบ", re.I)),
        page.locator('button[type="submit"]'),
        page.locator('[role="button"]').filter(has_text=re.compile(r"sign in|log in|login|เข้าสู่ระบบ", re.I)),
    ])
    if login_button is None:
        diagnostic = _save_diagnostic(page, output_dir, "login-button-not-found")
        raise SynologyWebCaptureError(f"ไม่พบปุ่ม Login DSM; ดูภาพตรวจสอบที่ {diagnostic}")
    login_button.click()
    page.wait_for_timeout(5_000)
    if _first_visible([page.locator('input[type="password"]')]) is not None:
        diagnostic = _save_diagnostic(page, output_dir, "login-failed")
        raise SynologyWebCaptureError(f"DSM Login ไม่สำเร็จ; ดูภาพตรวจสอบที่ {diagnostic}")


def _open_application(page, app_name: str, output_dir: Path):
    try:
        app = _text_locator(page, app_name, exact=True)
    except SynologyWebCaptureError:
        # Open DSM's main menu, then select the application by its visible name.
        menu = _first_visible([
            page.locator('[aria-label*="Main Menu" i]'),
            page.locator('[title*="Main Menu" i]'),
            page.locator('.x-tool-app'),
        ])
        if menu is not None:
            menu.click()
        else:
            # DSM 7 keeps the main-menu button at the top-left of the fixed
            # 1920x1080 desktop. This is only a UI click, not a network call.
            page.mouse.click(70, 30)
        page.wait_for_timeout(1_000)
        try:
            app = _text_locator(page, app_name, exact=True)
        except SynologyWebCaptureError as exc:
            diagnostic = _save_diagnostic(page, output_dir, "application-not-found")
            raise SynologyWebCaptureError(f"ไม่พบแอป {app_name} ใน DSM Main Menu; ดูภาพตรวจสอบที่ {diagnostic}") from exc
    app.dblclick(force=True)
    page.wait_for_timeout(5_000)
    return page


def _new_context(playwright, config: dict, output_dir: Path):
    browser_path, _runtime_dir, browser_env = _runtime(output_dir)
    browser = playwright.chromium.launch(
        executable_path=browser_path,
        headless=True,
        args=["--disable-gpu", "--disable-dev-shm-usage"],
        env=browser_env,
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=not bool(config.get("verify_ssl", True)),
        locale="en-US",
    )
    return browser, context


def download_daily_csv(
    config: dict,
    password: str,
    report_date: date,
    output_dir: Path,
) -> dict:
    """Download the exact dated CSV through the visible File Station UI only."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SynologyWebCaptureError("Playwright is not installed on the report server") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    expected_name = daily_csv_filename(report_date)
    root_url = _root_url(str(config.get("url") or ""))
    with sync_playwright() as playwright:
        browser, context = _new_context(playwright, config, output_dir)
        try:
            page = context.new_page()
            page.set_default_timeout(45_000)
            _login(page, root_url, str(config.get("username") or ""), password, output_dir)
            _open_application(page, "File Station", output_dir)
            file_window = _application_window(page, "File Station")

            # Navigate the visible folder tree. The exact dated filename is
            # still checked after the browser download completes.
            report_folder = _first_visible([
                file_window.get_by_text("ABB_Report", exact=True),
                page.get_by_text("ABB_Report", exact=True),
            ])
            if report_folder is None:
                backup_folder = _first_visible([
                    file_window.get_by_text("ABB_Backup", exact=True),
                    page.get_by_text("ABB_Backup", exact=True),
                ])
                if backup_folder is None:
                    diagnostic = _save_diagnostic(page, output_dir, "file-station-abb-backup-not-found")
                    raise SynologyWebCaptureError(f"ไม่พบโฟลเดอร์ ABB_Backup ใน File Station; ดูภาพตรวจสอบที่ {diagnostic}")
                backup_folder.dblclick(force=True)
                page.wait_for_timeout(1_500)
                report_folder = _first_visible([
                    file_window.get_by_text("ABB_Report", exact=True),
                    page.get_by_text("ABB_Report", exact=True),
                ])
            if report_folder is None:
                diagnostic = _save_diagnostic(page, output_dir, "file-station-abb-report-not-found")
                raise SynologyWebCaptureError(f"ไม่พบโฟลเดอร์ ABB_Report ใน File Station; ดูภาพตรวจสอบที่ {diagnostic}")
            report_folder.click(force=True)
            page.wait_for_timeout(2_500)

            target = _first_visible([
                file_window.get_by_text(expected_name, exact=True),
                page.get_by_text(expected_name, exact=True),
            ])
            if target is None:
                report_folder.dblclick(force=True)
                page.wait_for_timeout(2_500)
                target = _first_visible([
                    file_window.get_by_text(expected_name, exact=True),
                    page.get_by_text(expected_name, exact=True),
                ])
            if target is None:
                diagnostic = _save_diagnostic(page, output_dir, "file-station-dated-csv-not-found")
                raise SynologyWebCaptureError(
                    f"ไม่พบไฟล์ {expected_name} ใน ABB_Backup/ABB_Report; ดูภาพตรวจสอบที่ {diagnostic}"
                )
            target.click(force=True)
            page.wait_for_timeout(500)

            # DSM's toolbar is rendered outside the File Station window DOM
            # scope on this version. Use the selected file's context menu so
            # the download action remains anchored to the exact dated row and
            # does not depend on the unstable Action toolbar hierarchy.
            target.click(button="right", force=True)
            page.wait_for_timeout(500)
            try:
                # DSM renders the context menu in an application frame rather
                # than the main page. Search every live frame, as confirmed by
                # the diagnostic showing the visible Download menu item.
                download_button = _text_locator(page, "Download", exact=True)
            except SynologyWebCaptureError:
                try:
                    download_button = _text_locator(page, "ดาวน์โหลด", exact=True)
                except SynologyWebCaptureError:
                    download_button = None
            if download_button is None:
                diagnostic = _save_diagnostic(page, output_dir, "file-station-context-download-not-found")
                raise SynologyWebCaptureError(
                    f"คลิกขวาไฟล์ {expected_name} แล้วไม่พบคำสั่ง Download; ดูภาพตรวจสอบที่ {diagnostic}"
                )

            with page.expect_download(timeout=45_000) as download_info:
                download_button.click(force=True)
            download = download_info.value
            suggested_name = Path(download.suggested_filename).name
            require_exact_download_name(expected_name, suggested_name)
            output_path = output_dir / expected_name
            download.save_as(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise SynologyWebCaptureError(f"ไฟล์ที่ดาวน์โหลดจาก File Station ว่างเปล่า: {expected_name}")
            return {
                "ok": True,
                "name": expected_name,
                "path": str(output_path),
                "content": output_path.read_bytes(),
                "source_type": "file_station_browser_download",
            }
        finally:
            context.close()
            browser.close()


def capture_active_backup(
    config: dict,
    password: str,
    check_tasks: list[str],
    output_dir: Path,
) -> dict:
    """Capture DSM pages through Chromium only; no NAS API client is used."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SynologyWebCaptureError("Playwright is not installed on the report server") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    root_url = _root_url(str(config.get("url") or ""))
    with sync_playwright() as playwright:
        browser, context = _new_context(playwright, config, output_dir)
        try:
            page = context.new_page()
            page.set_default_timeout(45_000)
            _login(page, root_url, str(config.get("username") or ""), password, output_dir)
            _activate_application_window(page, "Active Backup for Business", output_dir)
            try:
                file_server_navigation = _left_navigation_locator(
                    page, "File Server"
                )
            except SynologyWebCaptureError as exc:
                diagnostic = _save_diagnostic(page, output_dir, "active-backup-file-server-navigation")
                raise SynologyWebCaptureError(
                    f"ไม่พบเมนู File Server ที่แถบซ้ายของ Active Backup; "
                    f"ดูภาพตรวจสอบที่ {diagnostic}"
                ) from exc
            file_server_navigation.click()
            page.wait_for_timeout(3_000)
            _open_active_backup_task_list(page, output_dir)
            overview_path = output_dir / "active_backup_task_list.png"
            page.screenshot(path=str(overview_path), full_page=False, type="png")

            captures: dict[str, list[str]] = {}
            for index, task_name in enumerate(check_tasks, start=1):
                _open_active_backup_details(page, task_name, output_dir)
                if task_name not in _body_text(page):
                    diagnostic = _save_diagnostic(page, output_dir, f"audit-{index}-task-mismatch")
                    raise SynologyWebCaptureError(f"หน้า Audit ไม่แสดง Task {task_name}; ดูภาพตรวจสอบที่ {diagnostic}")

                status_path = output_dir / f"audit_{index:02d}_status.png"
                page.screenshot(path=str(status_path), full_page=False, type="png")
                _open_active_backup_log(page, task_name, output_dir)
                log_path = output_dir / f"audit_{index:02d}_log.png"
                page.screenshot(path=str(log_path), full_page=False, type="png")

                body = _body_text(page)
                if "Detailed Information" not in body:
                    # Select the first visible log row. The selected task name
                    # remains visible and is checked again before acceptance.
                    if _click_first_data_row(page):
                        page.wait_for_timeout(1_500)
                body = _body_text(page)
                if "Detailed Information" not in body:
                    diagnostic = _save_diagnostic(page, output_dir, f"audit-{index}-detail-not-open")
                    raise SynologyWebCaptureError(
                        f"ไม่สามารถเปิด Detailed Information ของ Task {task_name}; ดูภาพตรวจสอบที่ {diagnostic}"
                    )
                if task_name not in body:
                    diagnostic = _save_diagnostic(page, output_dir, f"audit-{index}-detail-mismatch")
                    raise SynologyWebCaptureError(f"รายละเอียด Audit ไม่ตรงกับ Task {task_name}; ดูภาพตรวจสอบที่ {diagnostic}")
                detail_path = output_dir / f"audit_{index:02d}_detail.png"
                page.screenshot(path=str(detail_path), full_page=False, type="png")
                captures[task_name] = [str(status_path), str(log_path), str(detail_path)]

                closed = False
                for _ in range(3):
                    close_button = _first_visible([
                        page.get_by_role("button", name=re.compile(r"close|ปิด", re.I)),
                        page.locator('[aria-label*="Close" i]'),
                        page.locator('.x-tool-close'),
                    ])
                    if close_button is None:
                        break
                    close_button.click(force=True)
                    page.wait_for_timeout(800)
                    if "Task Name" in _body_text(page):
                        closed = True
                        break
                if not closed:
                    raise SynologyWebCaptureError("ไม่สามารถกลับไปหน้า Active Backup Task List หลัง Capture Audit")
            return {
                "ok": True,
                "overview_path": str(overview_path),
                "audit_captures": captures,
                "capture_method": "chromium_dsm_web_ui",
            }
        finally:
            context.close()
            browser.close()


def capture_yard(config: dict, password: str, output_dir: Path) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SynologyWebCaptureError("Playwright is not installed on the report server") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    root_url = _root_url(str(config.get("url") or ""))
    with sync_playwright() as playwright:
        browser, context = _new_context(playwright, config, output_dir)
        try:
            page = context.new_page()
            page.set_default_timeout(45_000)
            _login(page, root_url, str(config.get("username") or ""), password, output_dir)
            app_name = "Synology Drive ShareSync"
            try:
                _open_application(page, app_name, output_dir)
            except SynologyWebCaptureError:
                app_name = "Cloud Sync"
                _open_application(page, app_name, output_dir)
            _text_locator(page, "Synced folders", exact=True).click(force=True)
            page.wait_for_timeout(3_000)
            app_window = _application_window(page, app_name)
            box = app_window.bounding_box()
            if not box:
                diagnostic = _save_diagnostic(page, output_dir, "yard-window-bounds")
                raise SynologyWebCaptureError(f"อ่านขอบเขตหน้าต่าง Yard ไม่ได้; ดูภาพตรวจสอบที่ {diagnostic}")
            clip = {
                "x": max(0, box["x"]),
                "y": max(0, box["y"]),
                "width": min(1920 - max(0, box["x"]), box["width"]),
                "height": min(1080 - max(0, box["y"]), box["height"]),
            }
            before_png = page.screenshot(type="png", clip=clip)
            visible_up_to_date = _visible_exact_text_count(page, "Up to date")
            visible_two_way = _visible_exact_text_count(page, "Two-way sync")

            # The two supplied live diagnostics verify this fixed DSM toolbar
            # control: the list icon at x=120, y=70 relative to the ShareSync
            # window opens the read-only Sync log dialog. Validate the visible
            # result by pixel change instead of DSM's unstable DOM hierarchy.
            page.mouse.click(box["x"] + 120, box["y"] + 70)
            page.wait_for_timeout(2_500)
            after_png = page.screenshot(type="png", clip=clip)
            visual_change = _visual_change_ratio(before_png, after_png)
            if visual_change < 0.02:
                diagnostic = _save_diagnostic(page, output_dir, "yard-sync-log-no-visual-change")
                raise SynologyWebCaptureError(
                    f"กดเปิด Sync log แล้วแต่ภาพหน้าต่าง Yard เปลี่ยนเพียง {visual_change:.2%}; "
                    f"ดูภาพตรวจสอบที่ {diagnostic}"
                )
            output_path = output_dir / "yard_synced_folders.png"
            output_path.write_bytes(after_png)
            return {
                "ok": True,
                "path": str(output_path),
                "capture_method": "chromium_dsm_web_ui",
                "visible_up_to_date": visible_up_to_date,
                "visible_two_way_sync": visible_two_way,
                "sync_log_visual_change": visual_change,
            }
        finally:
            context.close()
            browser.close()
