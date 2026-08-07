from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from build_backup_report import REQUIRED_RESULT_COLUMNS, format_bytes
from synology_api import SynologyApiError, SynologyClient


STATUS = {2: "Successful", 3: "Warning", 4: "Failed"}
BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")
DEFAULT_ACTIVE_BACKUP_CSV = "/ABB_Backup/ABB_Report/abb_daily_result_latest.csv"


def _dt(epoch: Any) -> datetime:
    return datetime.fromtimestamp(int(epoch or 0), BANGKOK)


def _duration(start: int, end: int) -> str:
    seconds = max(0, int(end or 0) - int(start or 0))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _backup_group(task_name: str) -> str:
    upper_name = task_name.upper()
    if "BACKUP_VM" in upper_name or "VM_BACKUP" in upper_name or upper_name.startswith("VM_"):
        return "VM Backup"
    if "SQL" in upper_name or "_DB" in upper_name or "ALFDB" in upper_name:
        return "SQL Backup"
    return "File Backup"


def collect_active_backup_csv(
    client: SynologyClient,
    csv_path: str = DEFAULT_ACTIVE_BACKUP_CSV,
    report_hour: int = 9,
    now: datetime | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Use the NAS-generated daily result CSV as the authoritative ABB report."""
    report_hour = max(0, min(23, int(report_hour)))
    collected_at = now or datetime.now(BANGKOK)
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=BANGKOK)
    else:
        collected_at = collected_at.astimezone(BANGKOK)

    content = client.download(
        "SYNO.FileStation.Download",
        "download",
        {"path": csv_path, "mode": "download"},
        version=2,
    )
    if not content:
        raise ValueError(f"ไฟล์รายงานจาก NAS ว่างเปล่า: {csv_path}")
    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp874"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"ไม่สามารถอ่าน encoding ของไฟล์รายงานจาก NAS: {csv_path}")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = [str(name or "").lstrip("\ufeff").strip() for name in (reader.fieldnames or [])]
    missing_headers = [name for name in REQUIRED_RESULT_COLUMNS if name not in headers]
    if missing_headers:
        raise ValueError(
            "ไฟล์รายงานจาก NAS ขาดคอลัมน์ที่จำเป็น: " + ", ".join(missing_headers)
        )

    rows: list[dict[str, str]] = []
    report_dates = set()
    latest_result_time: datetime | None = None
    warning_total = error_total = 0
    for source_row in reader:
        if not any(str(value or "").strip() for value in source_row.values()):
            continue
        row = {
            str(key or "").lstrip("\ufeff").strip(): str(value or "").strip()
            for key, value in source_row.items()
        }
        normalized = {name: row.get(name, "") for name in REQUIRED_RESULT_COLUMNS}
        try:
            start = datetime.strptime(normalized["Start"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BANGKOK)
            end = datetime.strptime(normalized["End"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BANGKOK)
        except ValueError as exc:
            raise ValueError(
                f"รูปแบบวันเวลาใน CSV ไม่ถูกต้องที่รายการ {normalized.get('No.') or len(rows) + 1}: {exc}"
            ) from exc
        report_dates.add(start.date())
        latest_result_time = max(latest_result_time, end) if latest_result_time else end
        try:
            warning_text, error_text = normalized["Warning/Error"].split("/", 1)
            warning_total += int(warning_text.strip())
            error_total += int(error_text.strip())
        except (ValueError, TypeError):
            raise ValueError(
                f"ค่า Warning/Error ใน CSV ไม่ถูกต้องที่รายการ {normalized.get('No.') or len(rows) + 1}"
            )
        # A Check row gets a one-row evidence table sourced from the same
        # authoritative CSV; no independently calculated values are mixed in.
        normalized["_history"] = [{
            "Report Date": start.date().isoformat(),
            "Status": normalized["Status"],
            "Start": normalized["Start"],
            "End": normalized["End"],
            "Duration": normalized["Duration"],
            "Size": normalized["Size"],
            "File Count": normalized["File Count"],
            "Unchanged": normalized["Unchanged"],
            "Audit Same Size": normalized["Audit Same Size"],
            "Audit Status": normalized["Audit Status"],
        }]  # type: ignore[assignment]
        rows.append(normalized)

    if not rows:
        raise ValueError(f"ไม่พบรายการ Backup ในไฟล์รายงานจาก NAS: {csv_path}")
    if len(report_dates) != 1:
        raise ValueError("CSV จาก NAS มีข้อมูลมากกว่าหนึ่งวัน จึงไม่สร้างรายงานเพื่อป้องกันข้อมูลปะปน")
    report_date = next(iter(report_dates))
    if report_date != collected_at.date():
        raise ValueError(
            f"CSV จาก NAS เป็นข้อมูลวันที่ {report_date:%d/%m/%Y} แต่วันนี้คือ "
            f"{collected_at:%d/%m/%Y}; กรุณาตรวจสอบ Scheduled Task ที่สร้าง abb_daily_result_latest.csv"
        )

    scheduled_cutoff = datetime.combine(report_date, time(report_hour, 0), BANGKOK)
    effective_cutoff = min(collected_at, scheduled_cutoff)
    window_start = datetime.combine(report_date, time.min, BANGKOK)
    check_count = sum(1 for row in rows if row["Audit Status"].casefold() == "check")
    return rows, {
        "report_date": report_date,
        "row_count": len(rows),
        "task_count": len(rows),
        "result_count": len(rows),
        "missing_task_count": 0,
        "missing_tasks": [],
        "warning_total": warning_total,
        "error_total": error_total,
        "window_start": window_start,
        "scheduled_cutoff": scheduled_cutoff,
        "data_cutoff": effective_cutoff,
        "collected_at": collected_at,
        "latest_result_time": latest_result_time,
        "is_final_window": collected_at >= scheduled_cutoff,
        "source_api": f"SYNO.FileStation.Download ({csv_path})",
        "result_sha": hashlib.sha256(content).hexdigest(),
        "result_path": csv_path,
        "check_count": check_count,
    }


def cross_check_active_backup_api(
    client: SynologyClient,
    rows: list[dict[str, str]],
    report_date: date,
) -> dict[str, Any]:
    """Compare CSV task identity/status/timing with ABB API without overriding CSV."""
    tasks_data = client.call(
        "SYNO.ActiveBackup.Task",
        "list",
        {"filter": {}, "load_devices": True},
        version=1,
    )
    api_tasks = list(tasks_data.get("tasks") or [])
    history_data = client.call(
        "SYNO.ActiveBackup.Log",
        "list_result",
        {
            "filter": {},
            "offset": 0,
            "limit": 10000,
            "order_by": "time_start",
            "direction": "DESC",
        },
        version=1,
    )
    history = list(history_data.get("results") or [])

    def normalized_name(value: Any) -> str:
        return " ".join(str(value or "").split()).casefold()

    task_by_name: dict[str, dict[str, Any]] = {}
    task_by_id: dict[int, dict[str, Any]] = {}
    for task in api_tasks:
        task_id = int(task.get("task_id", -1))
        task_by_id[task_id] = task
        task_by_name[normalized_name(task.get("task_name"))] = task

    latest_today: dict[int, dict[str, Any]] = {}
    for result in history:
        task_id = int(result.get("task_id", -1))
        completed = _dt(result.get("time_end") or result.get("time_start"))
        if completed.date() != report_date or task_id not in task_by_id:
            continue
        existing = latest_today.get(task_id)
        if existing is None or int(result.get("time_start", 0) or 0) > int(existing.get("time_start", 0) or 0):
            latest_today[task_id] = result

    warnings: list[str] = []
    matched = 0
    csv_names = {normalized_name(row.get("Backup Task")) for row in rows}
    for row in rows:
        csv_name = str(row.get("Backup Task") or "-")
        task = task_by_name.get(normalized_name(csv_name))
        if not task:
            warnings.append(f"CSV task not found in Active Backup API: {csv_name}")
            continue
        result = latest_today.get(int(task.get("task_id", -1)))
        if not result:
            warnings.append(f"No Active Backup API result today for CSV task: {csv_name}")
            continue
        matched += 1
        api_status = STATUS.get(
            int(result.get("status", 0) or 0),
            f"Status {result.get('status', 0)}",
        )
        csv_status = str(row.get("Status") or "")
        if api_status.casefold() != csv_status.casefold():
            warnings.append(
                f"Status differs for {csv_name}: CSV={csv_status}; API={api_status}"
            )
        try:
            csv_end = datetime.strptime(
                str(row.get("End") or ""), "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=BANGKOK)
            api_end = _dt(result.get("time_end") or result.get("time_start"))
            if abs((api_end - csv_end).total_seconds()) > 300:
                warnings.append(
                    f"Latest result time differs for {csv_name}: "
                    f"CSV={csv_end:%Y-%m-%d %H:%M:%S}; API={api_end:%Y-%m-%d %H:%M:%S}"
                )
        except ValueError:
            warnings.append(f"Cannot compare result time for {csv_name}")

    extra_api_tasks = [
        str(task.get("task_name") or task.get("task_id"))
        for task in api_tasks
        if normalized_name(task.get("task_name")) not in csv_names
    ]
    if extra_api_tasks:
        warnings.append(
            "Active Backup API tasks absent from CSV: " + ", ".join(sorted(extra_api_tasks))
        )
    latest_api_result_time = max(
        (_dt(item.get("time_end") or item.get("time_start")) for item in latest_today.values()),
        default=None,
    )
    return {
        "checked": True,
        "consistent": not warnings,
        "warning_count": len(warnings),
        "warnings": warnings,
        "csv_task_count": len(rows),
        "api_task_count": len(api_tasks),
        "matched_result_count": matched,
        "api_result_count_today": len(latest_today),
        "latest_api_result_time": (
            latest_api_result_time.isoformat() if latest_api_result_time else None
        ),
        "comparison_fields": ["Backup Task", "Status", "End"],
        "authoritative_source": "abb_daily_result_latest.csv",
    }


def collect_active_backup(
    client: SynologyClient,
    alert_days: int = 7,
    report_hour: int = 9,
    now: datetime | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    alert_days = max(3, min(30, int(alert_days)))
    report_hour = max(0, min(23, int(report_hour)))
    collected_at = now or datetime.now(BANGKOK)
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=BANGKOK)
    else:
        collected_at = collected_at.astimezone(BANGKOK)
    report_date = collected_at.date()
    scheduled_cutoff = datetime.combine(report_date, time(report_hour, 0), BANGKOK)
    effective_cutoff = min(collected_at, scheduled_cutoff)
    window_start = datetime.combine(report_date, time.min, BANGKOK)
    is_final_window = collected_at >= scheduled_cutoff
    tasks_data = client.call(
        "SYNO.ActiveBackup.Task", "list",
        {"filter": {}, "load_devices": True}, version=1,
    )
    tasks = {int(item["task_id"]): item for item in tasks_data.get("tasks", [])}
    if not tasks:
        raise ValueError("Active Backup API ไม่พบ Backup Task ที่กำหนดค่าไว้")
    history = client.call(
        "SYNO.ActiveBackup.Log", "list_result",
        {"filter": {}, "offset": 0, "limit": 10000,
         "order_by": "time_start", "direction": "DESC"}, version=1,
    ).get("results", [])
    if not history:
        raise ValueError("Active Backup API ไม่พบประวัติการสำรองข้อมูล")

    def completed_at(item: dict[str, Any]) -> datetime:
        return _dt(item.get("time_end") or item.get("time_start"))

    current = [
        item for item in history
        if window_start <= completed_at(item) <= effective_cutoff
        and int(item.get("task_id", -1)) in tasks
    ]
    latest_by_task: dict[int, dict[str, Any]] = {}
    for item in current:
        task_id = int(item["task_id"])
        if task_id not in latest_by_task or int(item.get("time_start", 0)) > int(latest_by_task[task_id].get("time_start", 0)):
            latest_by_task[task_id] = item

    rows: list[dict[str, str]] = []
    warning_total = error_total = 0
    size_cache: dict[int, int] = {}

    def result_size(item: dict[str, Any]) -> int:
        result_id = int(item.get("result_id", 0) or 0)
        if result_id in size_cache:
            return size_cache[result_id]
        try:
            data = client.call("SYNO.ActiveBackup.Overview", "list_type_transfer_size", {"filter": {"result_id": result_id}}, version=1)
            size = sum(int(info.get("transfered_bytes", 0) or 0) for info in data.get("info_list", []))
        except SynologyApiError:
            size = int(item.get("transfered_bytes", 0) or 0)
        size_cache[result_id] = size
        return size

    for index, (task_id, result) in enumerate(sorted(latest_by_task.items(), key=lambda pair: int(pair[1].get("time_start", 0))), 1):
        task = tasks[task_id]
        task_name = str(task.get("task_name") or result.get("task_name") or task_id)
        group = _backup_group(task_name)
        start, end = int(result.get("time_start", 0)), int(result.get("time_end", 0))
        source = "-"
        devices = (result.get("task_config") or {}).get("device_list") or task.get("devices") or []
        if devices:
            source = str(devices[0].get("host_name") or devices[0].get("host_ip") or "-")
        warning = int(result.get("warning_count", 0) or 0)
        error = int(result.get("error_count", 0) or 0)
        warning_total += warning
        error_total += error
        status = STATUS.get(int(result.get("status", 0) or 0), f"Status {result.get('status', 0)}")
        transferred = result_size(result)
        daily_history: dict[object, dict[str, Any]] = {}
        for item in history:
            if int(item.get("task_id", -1)) != task_id:
                continue
            day = _dt(item.get("time_start")).date()
            if day not in daily_history or int(item.get("time_start", 0)) > int(daily_history[day].get("time_start", 0)):
                daily_history[day] = item
        task_history = sorted(daily_history.values(), key=lambda item: int(item.get("time_start", 0)), reverse=True)[:alert_days]
        same_size = sum(1 for item in task_history if result_size(item) == transferred)
        repeated_size = len(task_history) >= alert_days and same_size >= alert_days
        audit_status = "Check" if status != "Successful" or warning or error else "OK"
        note = (
            "พบ Warning/Error หรือสถานะไม่สำเร็จ กรุณาตรวจสอบรายละเอียดใน Active Backup"
            if audit_status == "Check"
            else f"ผลสำรองข้อมูลสำเร็จจาก Active Backup API; ขนาดข้อมูลเท่ากัน {same_size} วันจากช่วงเปรียบเทียบ {alert_days} วัน (ข้อมูลประกอบ)"
            if repeated_size
            else "ผลสำรองข้อมูลสำเร็จจาก Active Backup API"
        )
        history_rows = []
        for hist in sorted(task_history, key=lambda item: int(item.get("time_start", 0))):
            hist_start, hist_end = int(hist.get("time_start", 0)), int(hist.get("time_end", 0))
            hist_status = STATUS.get(int(hist.get("status", 0) or 0), f"Status {hist.get('status', 0)}")
            hist_warning = int(hist.get("warning_count", 0) or 0)
            hist_error = int(hist.get("error_count", 0) or 0)
            history_rows.append({
                "Report Date": _dt(hist_start).date().isoformat(), "Status": hist_status,
                "Start": _dt(hist_start).strftime("%Y-%m-%d %H:%M:%S"), "End": _dt(hist_end).strftime("%Y-%m-%d %H:%M:%S"),
                "Duration": _duration(hist_start, hist_end), "Size": format_bytes(str(result_size(hist))),
                "File Count": str(int(hist.get("success_count", 0) or 0)), "Unchanged": str(int(hist.get("none_count", 0) or 0)),
                "Audit Same Size": f"{same_size} of {alert_days}",
                "Audit Status": "Check" if hist_status != "Successful" or hist_warning or hist_error else "OK",
            })
        row = {
            "No.": str(index), "Group": group, "Backup Task": task_name,
            "Status": status, "Source": source,
            "Start": _dt(start).strftime("%Y-%m-%d %H:%M:%S"), "End": _dt(end).strftime("%Y-%m-%d %H:%M:%S"),
            "Duration": _duration(start, end), "Size": format_bytes(str(transferred)),
            "File Count": str(int(result.get("success_count", 0) or 0)), "Warning/Error": f"{warning} / {error}",
            "Unchanged": str(int(result.get("none_count", 0) or 0)), "Same Size": str(same_size), "Audit Same Size": f"{same_size} of {alert_days}",
            "Audit Status": audit_status, "Note": note,
        }
        row["_history"] = history_rows  # type: ignore[assignment]
        rows.append(row)

    missing_task_ids = sorted(set(tasks) - set(latest_by_task))
    for task_id in missing_task_ids:
        task = tasks[task_id]
        task_name = str(task.get("task_name") or task_id)
        group = _backup_group(task_name)
        devices = task.get("devices") or []
        source = "-"
        if devices:
            source = str(devices[0].get("host_name") or devices[0].get("host_ip") or "-")
        task_history = sorted(
            (item for item in history if int(item.get("task_id", -1)) == task_id),
            key=lambda item: int(item.get("time_start", 0)),
            reverse=True,
        )[:alert_days]
        history_rows = []
        for hist in sorted(task_history, key=lambda item: int(item.get("time_start", 0))):
            hist_start, hist_end = int(hist.get("time_start", 0)), int(hist.get("time_end", 0))
            hist_status = STATUS.get(int(hist.get("status", 0) or 0), f"Status {hist.get('status', 0)}")
            hist_warning = int(hist.get("warning_count", 0) or 0)
            hist_error = int(hist.get("error_count", 0) or 0)
            history_rows.append({
                "Report Date": _dt(hist_start).date().isoformat(), "Status": hist_status,
                "Start": _dt(hist_start).strftime("%Y-%m-%d %H:%M:%S"), "End": _dt(hist_end).strftime("%Y-%m-%d %H:%M:%S"),
                "Duration": _duration(hist_start, hist_end), "Size": format_bytes(str(result_size(hist))),
                "File Count": str(int(hist.get("success_count", 0) or 0)), "Unchanged": str(int(hist.get("none_count", 0) or 0)),
                "Audit Same Size": f"- of {alert_days}",
                "Audit Status": "Check" if hist_status != "Successful" or hist_warning or hist_error else "OK",
            })
        rows.append({
            "No.": str(len(rows) + 1), "Group": group, "Backup Task": task_name,
            "Status": f"No result by {effective_cutoff:%H:%M}", "Source": source,
            "Start": "", "End": "", "Duration": "-", "Size": "-",
            "File Count": "-", "Warning/Error": "0 / 0", "Unchanged": "-",
            "Same Size": "-", "Audit Same Size": f"- of {alert_days}",
            "Audit Status": "Check",
            "Note": f"NAS API ไม่พบผลสำรองข้อมูลของงานนี้ในรอบ {window_start:%H:%M}-{effective_cutoff:%H:%M} วันที่ {report_date:%d/%m/%Y}",
            "_history": history_rows,
        })

    latest_result_time = max((completed_at(item) for item in current), default=None)
    return rows, {
        "report_date": report_date,
        "row_count": len(rows),
        "task_count": len(tasks),
        "result_count": len(latest_by_task),
        "missing_task_count": len(missing_task_ids),
        "missing_tasks": [str(tasks[task_id].get("task_name") or task_id) for task_id in missing_task_ids],
        "warning_total": warning_total,
        "error_total": error_total,
        "window_start": window_start,
        "scheduled_cutoff": scheduled_cutoff,
        "data_cutoff": effective_cutoff,
        "collected_at": collected_at,
        "latest_result_time": latest_result_time,
        "is_final_window": is_final_window,
        "source_api": "SYNO.ActiveBackup.Task + SYNO.ActiveBackup.Log + SYNO.ActiveBackup.Overview",
    }


def _first_value(item: dict[str, Any], *keys: str, default: Any = "-") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return default


def _list_values(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("conn", "connections", "connection", "sessions", "session", "items", "logs", "log"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_cloud_connection(item: dict[str, Any], index: int) -> dict[str, str]:
    return {
        "name": str(_first_value(item, "display_name", "name", "conn_name", "task_name", default=f"Connection {index}")),
        "provider": str(_first_value(item, "provider", "cloud_type", "service", "type")),
        "local_path": str(_first_value(item, "local_path", "sync_folder", "local_folder", "path")),
        "remote_path": str(_first_value(item, "remote_path", "remote_folder", "cloud_path")),
        "status": str(_first_value(item, "sync_status", "status", "state", "last_status", default="unknown")),
    }


def _normalize_cloud_log(item: dict[str, Any]) -> dict[str, str]:
    return {
        "time": str(_first_value(item, "time", "datetime", "date", "timestamp")),
        "level": str(_first_value(item, "level", "severity", "priority", "status")),
        "message": str(_first_value(item, "message", "msg", "description", "event", "log")),
    }


def _sharesync_status(value: Any) -> str:
    raw = str(value or "unknown").strip().lower()
    labels = {
        "uptodate": "Up to date",
        "syncing": "Syncing",
        "connecting": "Connecting",
        "pause": "Paused",
        "stop": "Stopped",
        "unlink": "Unlinked",
    }
    if raw.startswith("err_"):
        return f"Error ({raw[4:].replace('_', ' ')})"
    return labels.get(raw, str(value or "Unknown"))


def _sharesync_direction(value: Any) -> str:
    raw = str(value if value is not None else "").strip().lower()
    return {
        "0": "Two-way sync",
        "two_way": "Two-way sync",
        "two-way": "Two-way sync",
        "bidirectional": "Two-way sync",
        "1": "Upload only",
        "upload": "Upload only",
        "2": "Download only",
        "download": "Download only",
    }.get(raw, str(value or "-"))


def _sharesync_time(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return str(value or "-")
    return datetime.fromtimestamp(numeric, BANGKOK).strftime("%Y-%m-%d %H:%M:%S")


def collect_drive_sharesync(client: SynologyClient) -> dict[str, Any]:
    """Collect the same Synology Drive ShareSync data shown by DSM's Synced folders page."""
    connection_api = "SYNO.SynologyDriveShareSync.Connection"
    session_api = "SYNO.SynologyDriveShareSync.Session"
    definitions = client.discover([connection_api, session_api])
    missing = [api for api in (connection_api, session_api) if api not in definitions]
    if missing:
        raise SynologyApiError("Drive ShareSync API is not available: " + ", ".join(missing))

    connection_data = client.call(connection_api, "list", version=1)
    raw_connections = _list_values(connection_data)
    sync_folders: list[dict[str, str]] = []
    errors: dict[str, str] = {}
    methods = [f"{connection_api}.list"]

    for connection in raw_connections:
        conn_id = _first_value(connection, "id", "conn_id", default="")
        if conn_id == "":
            continue
        try:
            session_data = client.call(
                session_api,
                "list",
                {"conn_id": conn_id, "offset": 0, "limit": 1024},
                version=1,
            )
            methods.append(f"{session_api}.list")
        except SynologyApiError as exc:
            errors[f"session_{conn_id}"] = str(exc)
            continue
        for item in _list_values(session_data):
            enabled = bool(_first_value(item, "enable", "enabled", default=True))
            raw_status = _first_value(item, "status", "db_status", default="unknown")
            sync_folders.append({
                "name": str(_first_value(item, "remote_share", "local_share", default="-")),
                "provider": "Synology Drive ShareSync",
                "local_path": str(_first_value(item, "local_share", default="-")),
                "remote_path": str(_first_value(item, "remote_share", default="-")),
                "sync_direction": _sharesync_direction(_first_value(item, "sync_direction", default="0")),
                "status": _sharesync_status(raw_status),
                "raw_status": str(raw_status),
                "enabled": "Yes" if enabled else "No",
                "connection": str(_first_value(connection, "server_name", "name", default=conn_id)),
            })

    logs: list[dict[str, str]] = []
    try:
        history_data = client.call(
            session_api,
            "list_sync_history",
            {"offset": 0, "limit": 200, "sess_id": 0},
            version=1,
        )
        methods.append(f"{session_api}.list_sync_history")
        history_items = history_data.get("history_items", [])
        if isinstance(history_items, list):
            for item in history_items:
                if not isinstance(item, dict):
                    continue
                action = str(_first_value(item, "action", default="-")).replace("_", " ").title()
                path = str(_first_value(item, "path", default="-"))
                normalized_path = path.replace("\\", "/").rstrip("/")
                name = normalized_path.rsplit("/", 1)[-1] if normalized_path else path
                raw_item_type = _first_value(
                    item, "item_type", "file_type", "type", default=""
                )
                raw_is_dir = str(_first_value(item, "is_dir", "is_folder", default="")).lower()
                if raw_is_dir in {"1", "true", "yes"}:
                    item_type = "Folder"
                elif str(raw_item_type).strip():
                    normalized_type = str(raw_item_type).strip().lower()
                    item_type = {
                        "0": "File",
                        "1": "Folder",
                        "file": "File",
                        "folder": "Folder",
                        "dir": "Folder",
                        "directory": "Folder",
                    }.get(
                        normalized_type,
                        str(raw_item_type).replace("_", " ").title(),
                    )
                else:
                    item_type = "Folder" if path.endswith(("/", "\\")) else "File"
                logs.append({
                    "time": _sharesync_time(_first_value(item, "time", default="")),
                    "level": action,
                    "name": name,
                    "event": action,
                    "item_type": item_type,
                    "path": path,
                    "message": f"{action}: {path}",
                })
    except SynologyApiError as exc:
        errors["sync_history"] = str(exc)

    sync_folders.sort(key=lambda item: item["local_path"].casefold())
    logs.sort(key=lambda item: item["time"], reverse=True)
    enabled_folders = [item for item in sync_folders if item["enabled"] == "Yes"]
    up_to_date_count = sum(1 for item in enabled_folders if item["raw_status"].lower() == "uptodate")
    paused = any(item["raw_status"].lower() in {"pause", "stop"} for item in enabled_folders)
    healthy = bool(enabled_folders) and up_to_date_count == len(enabled_folders)
    connection_statuses = [
        str(_first_value(item, "status", default="unknown")) for item in raw_connections
    ]
    if healthy:
        tray_status = "Up to date"
        readiness = "ready"
    elif not enabled_folders:
        tray_status = "No synced folders"
        readiness = "no_connections"
    else:
        tray_status = "Attention required"
        readiness = "attention"

    return {
        "source_type": "drive_sharesync",
        "source_label": "Synology Drive ShareSync Web API",
        "connection_count": len(enabled_folders),
        "storage_connection_count": len(raw_connections),
        "up_to_date_count": up_to_date_count,
        "healthy": healthy,
        "paused": paused,
        "tray_status": tray_status,
        "connection_statuses": connection_statuses,
        "connections": sync_folders,
        "logs": logs[:50],
        "api_methods": sorted(set(methods)),
        "api_errors": errors,
        "api_connected": True,
        "has_connections": bool(enabled_folders),
        "readiness": readiness,
    }


def collect_cloud_sync(client: SynologyClient) -> dict[str, Any]:
    responses: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for method in ("list_conn", "list_session", "get_status"):
        try:
            responses[method] = client.call("SYNO.CloudSync", method, version=1)
        except SynologyApiError as exc:
            errors[method] = str(exc)

    if not responses:
        raise SynologyApiError("Cloud Sync API ไม่ตอบกลับ: " + "; ".join(errors.values()))

    raw_connections: list[dict[str, Any]] = []
    for data in responses.values():
        raw_connections.extend(_list_values(data))
    connections: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(raw_connections, 1):
        normalized = _normalize_cloud_connection(item, index)
        identity = (normalized["name"], normalized["local_path"], normalized["remote_path"])
        if identity not in seen:
            seen.add(identity)
            connections.append(normalized)

    combined = {key: value for data in responses.values() for key, value in data.items()}
    logs: list[dict[str, str]] = []
    try:
        log_data = client.call("SYNO.LogCenter.Log", "list", {"offset": 0, "limit": 500})
        for item in _list_values(log_data):
            searchable = json.dumps(item, ensure_ascii=False).lower()
            if "cloud sync" in searchable or "cloudsync" in searchable:
                logs.append(_normalize_cloud_log(item))
    except SynologyApiError as exc:
        errors["log_center"] = str(exc)

    reported_total = _first_value(combined, "total", "connection_count", default=len(connections))
    try:
        connection_count = max(int(reported_total or 0), len(connections))
    except (TypeError, ValueError):
        connection_count = len(connections)
    api_connected = "list_conn" in responses
    has_connections = connection_count > 0 or bool(connections)
    paused = bool(_first_value(combined, "is_pause", "paused", default=False))
    tray_status = str(
        _first_value(combined, "tray_status", "sync_status", "status", "state", default="unknown")
    )
    if not api_connected:
        readiness = "api_unavailable"
    elif not has_connections:
        readiness = "no_connections"
    elif paused or tray_status.lower() in {"suspended", "paused", "stopped"}:
        readiness = "paused"
    else:
        readiness = "ready"

    return {
        "connection_count": connection_count,
        "paused": paused,
        "tray_status": tray_status,
        "connections": connections,
        "logs": logs[:50],
        "api_methods": sorted(responses),
        "api_errors": errors,
        "api_connected": api_connected,
        "has_connections": has_connections,
        "readiness": readiness,
    }
