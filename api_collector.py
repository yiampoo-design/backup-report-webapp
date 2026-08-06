from __future__ import annotations

from datetime import datetime
from typing import Any

from build_backup_report import format_bytes
from synology_api import SynologyApiError, SynologyClient


STATUS = {2: "Successful", 3: "Warning", 4: "Failed"}


def _dt(epoch: Any) -> datetime:
    return datetime.fromtimestamp(int(epoch or 0))


def _duration(start: int, end: int) -> str:
    seconds = max(0, int(end or 0) - int(start or 0))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def collect_active_backup(client: SynologyClient, alert_days: int = 3) -> tuple[list[dict[str, str]], dict[str, Any]]:
    tasks_data = client.call(
        "SYNO.ActiveBackup.Task", "list",
        {"filter": {"backup_type": 4}, "load_devices": True}, version=1,
    )
    tasks = {int(item["task_id"]): item for item in tasks_data.get("tasks", [])}
    history = client.call(
        "SYNO.ActiveBackup.Log", "list_result",
        {"filter": {"backup_type": 4}, "offset": 0, "limit": 10000,
         "order_by": "time_start", "direction": "DESC"}, version=1,
    ).get("results", [])
    if not history:
        raise ValueError("Active Backup API ไม่พบประวัติการสำรองข้อมูล")
    latest_date = max(_dt(item.get("time_start")).date() for item in history)
    current = [item for item in history if _dt(item.get("time_start")).date() == latest_date and int(item.get("task_id", -1)) in tasks]
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
        upper_name = task_name.upper()
        group = "SQL Backup" if ("SQL" in upper_name or "_DB" in upper_name or "ALFDB" in upper_name) else "File Backup"
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
        repeated_size = group == "File Backup" and len(task_history) >= alert_days and same_size >= alert_days
        audit_status = "Check" if status != "Successful" or warning or error or repeated_size else "OK"
        note = (f"ขนาดข้อมูลเท่ากัน {same_size} ครั้งในช่วงตรวจ {alert_days} ครั้ง กรุณาตรวจสอบข้อมูลต้นทาง" if repeated_size else
                "พบ Warning/Error หรือสถานะไม่สำเร็จ กรุณาตรวจสอบรายละเอียดใน Active Backup" if audit_status == "Check" else
                "ผลสำรองข้อมูลสำเร็จจาก Active Backup API")
        history_rows = []
        for hist in sorted(task_history, key=lambda item: int(item.get("time_start", 0))):
            hist_start, hist_end = int(hist.get("time_start", 0)), int(hist.get("time_end", 0))
            hist_status = STATUS.get(int(hist.get("status", 0) or 0), f"Status {hist.get('status', 0)}")
            history_rows.append({
                "Report Date": _dt(hist_start).date().isoformat(), "Status": hist_status,
                "Start": _dt(hist_start).strftime("%Y-%m-%d %H:%M:%S"), "End": _dt(hist_end).strftime("%Y-%m-%d %H:%M:%S"),
                "Duration": _duration(hist_start, hist_end), "Size": format_bytes(str(result_size(hist))),
                "File Count": str(int(hist.get("success_count", 0) or 0)), "Unchanged": str(int(hist.get("none_count", 0) or 0)),
                "Audit Same Size": f"{same_size} of {alert_days}", "Audit Status": "Check" if repeated_size else "OK",
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
    if not rows:
        raise ValueError(f"ไม่พบผล Active Backup ประจำวันที่ {latest_date:%d/%m/%Y}")
    return rows, {"report_date": latest_date, "row_count": len(rows), "warning_total": warning_total, "error_total": error_total}


def collect_cloud_sync(client: SynologyClient) -> dict[str, Any]:
    data = client.call("SYNO.CloudSync", "list_conn", version=1)
    return {
        "connection_count": int(data.get("total", len(data.get("conn", []))) or 0),
        "paused": bool(data.get("is_pause", False)),
        "tray_status": str(data.get("tray_status", "unknown")),
    }
