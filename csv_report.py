from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")
DAILY_FILENAME = re.compile(r"^abb_daily_result_(\d{4}-\d{2}-\d{2})\.csv$", re.IGNORECASE)
ACTIVE_BACKUP_DAILY_COLUMNS = [
    "No.", "Group", "Backup Task", "Status", "Source", "Last Backup",
    "Duration", "Size", "File Count", "Warning/Error", "Unchanged",
    "Same Size", "Audit Same Size", "Audit Status", "Note",
]

# Display order shown by Active Backup for Business > File Server > Task List.
# CSV values remain authoritative; only row position and the displayed No. are changed.
ACTIVE_BACKUP_TASK_LIST_ORDER = [
    "STOCK_Backup_APP_SQLBak_0000",
    "EXPRESS_Backup_Full_0000",
    "ERP-WEB_Backup_APCHE_PHP_WebApp_0000",
    "ERP-DB_Backup_SQLBak_0000",
    "MOBILE_Backup_WebApp_0000",
    "TIGERSOFT_Backup_Payroll_0000",
    "TIGERSOFT2023_Backup_APP_0000",
    "TIGERSOFT2023_Backup_DB_0000",
    "ERP-APP-Demo_Backup_WebApp_0015",
    "ERP-DB-Demo_Backup_SQLBak_0015",
    "ERP-TEST_Backup_WebApp-SQLBak_0030",
    "ALFRESCO-DB_Backup_AlfDB_0100",
    "ALFRESCO-WEB_Backup_Content_0130",
    "MA-APP_Backup_Web_SQLBak_0200",
]


def order_rows_like_task_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match DSM Task List order without changing authoritative CSV field values."""
    order = {
        task_name.casefold(): position
        for position, task_name in enumerate(ACTIVE_BACKUP_TASK_LIST_ORDER)
    }
    fallback = len(order)
    ordered = sorted(
        enumerate(rows),
        key=lambda item: (
            order.get(str(item[1].get("Backup Task") or "").casefold(), fallback),
            item[0],
        ),
    )
    result: list[dict[str, Any]] = []
    for displayed_no, (_, source_row) in enumerate(ordered, start=1):
        row = dict(source_row)
        row["_csv_no"] = source_row.get("No.")
        row["No."] = str(displayed_no)
        result.append(row)
    return result


def _decode_csv(content: bytes, filename: str) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp874"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"ไม่สามารถอ่าน encoding ของไฟล์ CSV: {filename}")


def _parse_audit_blocks(records: list[list[str]]) -> dict[str, dict[str, str]]:
    details: dict[str, dict[str, str]] = {}
    index = 0
    while index < len(records):
        current = [str(value or "").strip() for value in records[index]]
        if len(current) == 1 and current[0].startswith("Audit "):
            label = current[0]
            index += 1
            while index < len(records) and not any(str(value).strip() for value in records[index]):
                index += 1
            if index >= len(records):
                break
            task_name = str(records[index][0] if records[index] else "").strip()
            index += 1
            values: dict[str, str] = {"Audit Label": label}
            while index < len(records):
                row = [str(value or "").strip() for value in records[index]]
                if len(row) == 1 and row[0].startswith("Audit "):
                    break
                if len(row) >= 2 and row[0] not in {"", "รายการ"}:
                    values[row[0]] = row[1]
                index += 1
            if task_name:
                details[task_name] = values
            continue
        index += 1
    return details


def parse_uploaded_daily_csv(
    content: bytes,
    filename: str,
    report_hour: int = 9,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse the exact daily CSV selected by the operator; no NAS access occurs."""
    safe_name = Path(filename).name
    match = DAILY_FILENAME.fullmatch(safe_name)
    if not match:
        raise ValueError(
            "ชื่อไฟล์ต้องเป็น abb_daily_result_YYYY-MM-DD.csv เท่านั้น"
        )
    filename_date = date.fromisoformat(match.group(1))
    if not content:
        raise ValueError("ไฟล์ CSV ที่อัปโหลดว่างเปล่า")
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("ไฟล์ CSV มีขนาดเกิน 5 MB")

    records = list(csv.reader(io.StringIO(_decode_csv(content, safe_name), newline="")))
    if not records:
        raise ValueError("ไฟล์ CSV ที่อัปโหลดว่างเปล่า")
    headers = [str(name or "").lstrip("\ufeff").strip() for name in records[0]]
    if headers != ACTIVE_BACKUP_DAILY_COLUMNS:
        raise ValueError(
            "รูปแบบ CSV ไม่ตรงกับรายงานที่อนุมัติ: "
            f"expected={ACTIVE_BACKUP_DAILY_COLUMNS}; observed={headers}"
        )

    audit_marker = next(
        (
            index for index, record in enumerate(records[1:], start=1)
            if len(record) == 1 and str(record[0]).strip().upper() == "AUDIT"
        ),
        len(records),
    )
    main_records = [
        record for record in records[1:audit_marker]
        if any(str(value).strip() for value in record)
    ]
    audit_details = _parse_audit_blocks(
        records[audit_marker + 1:] if audit_marker < len(records) else []
    )

    rows: list[dict[str, Any]] = []
    report_dates: set[date] = set()
    latest_result_time: datetime | None = None
    warning_total = 0
    error_total = 0
    for position, record in enumerate(main_records, start=1):
        if len(record) != len(ACTIVE_BACKUP_DAILY_COLUMNS):
            raise ValueError(
                f"จำนวนคอลัมน์รายการที่ {position} ไม่ถูกต้อง: "
                f"expected {len(ACTIVE_BACKUP_DAILY_COLUMNS)}, observed {len(record)}"
            )
        row: dict[str, Any] = dict(zip(
            ACTIVE_BACKUP_DAILY_COLUMNS,
            (str(value or "").strip() for value in record),
        ))
        try:
            start = datetime.strptime(row["Last Backup"], "%d/%m/%Y %H:%M:%S").replace(tzinfo=BANGKOK)
        except ValueError as exc:
            raise ValueError(
                f"Last Backup รายการที่ {row.get('No.') or position} ไม่อยู่ในรูปแบบ DD/MM/YYYY HH:MM:SS"
            ) from exc
        row["Start"] = start.strftime("%Y-%m-%d %H:%M:%S")
        row["_audit_detail"] = audit_details.get(str(row["Backup Task"]), {})
        report_dates.add(start.date())
        latest_result_time = max(latest_result_time, start) if latest_result_time else start
        try:
            warning_text, error_text = str(row["Warning/Error"]).split("/", 1)
            warning_total += int(warning_text.strip())
            error_total += int(error_text.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Warning/Error รายการที่ {row.get('No.') or position} ไม่ถูกต้อง") from exc
        rows.append(row)

    if not rows:
        raise ValueError("ไม่พบรายการ Backup ในไฟล์ CSV")
    if report_dates != {filename_date}:
        found = ", ".join(sorted(value.isoformat() for value in report_dates)) or "-"
        raise ValueError(
            f"วันที่ในชื่อไฟล์ ({filename_date.isoformat()}) ไม่ตรงกับ Last Backup ({found})"
        )

    check_tasks = {
        str(row["Backup Task"]) for row in rows
        if str(row["Audit Status"]).casefold() == "check"
    }
    if check_tasks != set(audit_details):
        raise ValueError(
            "รายการ Check และส่วน AUDIT ใน CSV ไม่ตรงกัน: "
            f"Check={sorted(check_tasks)}; AUDIT={sorted(audit_details)}"
        )

    rows = order_rows_like_task_list(rows)

    collected_at = now or datetime.now(BANGKOK)
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=BANGKOK)
    else:
        collected_at = collected_at.astimezone(BANGKOK)
    if filename_date != collected_at.date():
        raise ValueError(
            f"ไฟล์เป็นข้อมูลวันที่ {filename_date:%d/%m/%Y} แต่วันนี้คือ {collected_at:%d/%m/%Y}"
        )

    report_hour = max(0, min(23, int(report_hour)))
    window_start = datetime.combine(filename_date, time.min, BANGKOK)
    scheduled_cutoff = datetime.combine(filename_date, time(report_hour), BANGKOK)
    return rows, {
        "report_date": filename_date,
        "row_count": len(rows),
        "task_count": len(rows),
        "result_count": len(rows),
        "missing_task_count": 0,
        "missing_tasks": [],
        "warning_total": warning_total,
        "error_total": error_total,
        "window_start": window_start,
        "scheduled_cutoff": scheduled_cutoff,
        "data_cutoff": min(collected_at, scheduled_cutoff),
        "collected_at": collected_at,
        "latest_result_time": latest_result_time,
        "is_final_window": collected_at >= scheduled_cutoff,
        "source_type": "manual_csv_upload",
        "source_api": "",
        "result_path": safe_name,
        "result_sha": hashlib.sha256(content).hexdigest(),
        "schema_sha": hashlib.sha256(",".join(headers).encode("utf-8")).hexdigest(),
        "used_dated_fallback": False,
        "check_count": len(check_tasks),
    }
