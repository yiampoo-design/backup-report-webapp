from __future__ import annotations

import csv
import hashlib
import html
import os
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "pdf"
DEFAULT_LOGO_PATH = ROOT / "web" / "icon.png"

REQUIRED_RESULT_COLUMNS = [
    "No.", "Group", "Backup Task", "Status", "Source", "Start", "End",
    "Duration", "Size", "File Count", "Warning/Error", "Unchanged",
    "Same Size", "Audit Same Size", "Audit Status", "Note",
]
REQUIRED_RAW_COLUMNS = [
    "result_id", "task_id", "Group", "task_name", "status", "source",
    "start_time", "end_time", "duration", "transfered_bytes",
    "success_count", "warning_count", "error_count", "none_count",
    "alert_days",
]

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#1F6F9F")
LIGHT_BLUE = colors.HexColor("#EAF3F8")
PALE = colors.HexColor("#F5F7F9")
GRID = colors.HexColor("#CBD5DD")
TEXT = colors.HexColor("#20303C")
MUTED = colors.HexColor("#667782")
GREEN = colors.HexColor("#14834A")
GREEN_BG = colors.HexColor("#E9F6EF")
AMBER = colors.HexColor("#A65E00")
AMBER_BG = colors.HexColor("#FFF3D6")
RED = colors.HexColor("#B83232")
RED_BG = colors.HexColor("#FDEAEA")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_bytes(value: str) -> str:
    size = int(value)
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.2f} GB"
    if size >= 1024 ** 2:
        return f"{size / 1024 ** 2:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.2f} KB"
    return f"{size} Bytes"


def validate_and_reconcile(
    result_fields: list[str],
    result_rows: list[dict[str, str]],
    raw_fields: list[str],
    raw_rows: list[dict[str, str]],
    result_path: Path,
    raw_path: Path,
) -> dict[str, object]:
    if result_fields != REQUIRED_RESULT_COLUMNS:
        raise ValueError(f"Unexpected result CSV schema: {result_fields}")
    if raw_fields != REQUIRED_RAW_COLUMNS:
        raise ValueError(f"Unexpected raw CSV schema: {raw_fields}")
    if not result_rows:
        raise ValueError("Result CSV has no rows")
    if len(result_rows) != len(raw_rows):
        raise ValueError(
            f"Row-count mismatch: result={len(result_rows)}, raw={len(raw_rows)}"
        )

    raw_by_task: dict[str, dict[str, str]] = {}
    for row in raw_rows:
        task = row["task_name"]
        if task in raw_by_task:
            raise ValueError(f"Duplicate task in raw CSV: {task}")
        raw_by_task[task] = row

    mismatches: list[str] = []
    for row in result_rows:
        task = row["Backup Task"]
        raw = raw_by_task.get(task)
        if raw is None:
            mismatches.append(f"Missing raw task: {task}")
            continue
        checks = {
            "Group": (row["Group"], raw["Group"]),
            "Status": (row["Status"], raw["status"]),
            "Source": (row["Source"], raw["source"]),
            "Start": (row["Start"], raw["start_time"]),
            "End": (row["End"], raw["end_time"]),
            "Duration": (row["Duration"], raw["duration"]),
            "Size": (row["Size"], format_bytes(raw["transfered_bytes"])),
            "File Count": (row["File Count"], raw["success_count"]),
            "Warning/Error": (
                row["Warning/Error"],
                f"{raw['warning_count']} / {raw['error_count']}",
            ),
            "Unchanged": (row["Unchanged"], raw["none_count"]),
        }
        for label, (actual, expected) in checks.items():
            if actual != expected:
                mismatches.append(
                    f"{task} [{label}] result={actual!r} raw={expected!r}"
                )
    if mismatches:
        raise ValueError("CSV reconciliation failed:\n" + "\n".join(mismatches[:20]))

    starts = [datetime.strptime(r["Start"], "%Y-%m-%d %H:%M:%S") for r in result_rows]
    report_dates = {value.date() for value in starts}
    if len(report_dates) != 1:
        raise ValueError(f"Multiple report dates found: {sorted(report_dates)}")

    warning_total = sum(int(r["warning_count"]) for r in raw_rows)
    error_total = sum(int(r["error_count"]) for r in raw_rows)
    return {
        "report_date": report_dates.pop(),
        "row_count": len(result_rows),
        "warning_total": warning_total,
        "error_total": error_total,
        "result_sha": file_sha256(result_path),
        "raw_sha": file_sha256(raw_path),
        "result_path": result_path,
        "raw_path": raw_path,
    }


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def p(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(esc(value), style)


def short_dt(value: str) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%d/%m/%Y %H:%M")


def time_only(value: str) -> str:
    if not value:
        return "-"
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%H:%M:%S")


def load_task_history(
    task_name: str,
    report_date,
    days: int = 3,
    history_dir: Path | None = None,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    if history_dir is None:
        return history
    source_dir = history_dir
    for offset in range(days - 1, -1, -1):
        day = report_date - timedelta(days=offset)
        source = source_dir / f"abb_daily_result_{day.isoformat()}.csv"
        if not source.exists():
            continue
        fields, rows = read_csv(source)
        if fields != REQUIRED_RESULT_COLUMNS:
            raise ValueError(f"Unexpected historical CSV schema: {source.name}")
        matches = [row for row in rows if row["Backup Task"] == task_name]
        if len(matches) > 1:
            raise ValueError(f"Duplicate historical task in {source.name}: {task_name}")
        if matches:
            item = dict(matches[0])
            item["Report Date"] = day.isoformat()
            history.append(item)
    return history


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleThai", parent=base["Title"], fontName="Tahoma-Bold",
            fontSize=18, leading=22, textColor=NAVY, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Tahoma",
            fontSize=8.5, leading=11, textColor=MUTED,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName="Tahoma-Bold",
            fontSize=10.5, leading=13, textColor=NAVY, spaceBefore=2, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName="Tahoma",
            fontSize=8, leading=11, textColor=TEXT,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"], fontName="Tahoma",
            fontSize=6.7, leading=8.2, textColor=TEXT,
        ),
        "small_center": ParagraphStyle(
            "SmallCenter", parent=base["Normal"], fontName="Tahoma",
            fontSize=6.7, leading=8.2, textColor=TEXT, alignment=TA_CENTER,
        ),
        "small_right": ParagraphStyle(
            "SmallRight", parent=base["Normal"], fontName="Tahoma",
            fontSize=6.7, leading=8.2, textColor=TEXT, alignment=TA_RIGHT,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", parent=base["Normal"], fontName="Tahoma-Bold",
            fontSize=6.7, leading=8, textColor=colors.white, alignment=TA_CENTER,
        ),
        "tile_label": ParagraphStyle(
            "TileLabel", parent=base["Normal"], fontName="Tahoma",
            fontSize=7.3, leading=9, textColor=MUTED, alignment=TA_CENTER,
        ),
        "tile_value": ParagraphStyle(
            "TileValue", parent=base["Normal"], fontName="Tahoma-Bold",
            fontSize=14, leading=17, textColor=NAVY, alignment=TA_CENTER,
        ),
        "note": ParagraphStyle(
            "Note", parent=base["Normal"], fontName="Tahoma",
            fontSize=7.2, leading=10, textColor=MUTED,
        ),
    }


def summary_tiles(result_rows: list[dict[str, str]], audit: dict[str, object], styles):
    total = len(result_rows)
    successful = sum(r["Status"] == "Successful" for r in result_rows)
    checks = sum(r["Audit Status"] == "Check" for r in result_rows)
    non_success = total - successful
    warnings = int(audit["warning_total"])
    errors = int(audit["error_total"])
    tiles = [
        ("งานทั้งหมด / Total", str(total), NAVY),
        ("สำเร็จ / Successful", str(successful), GREEN),
        ("ต้องตรวจสอบ / Check", str(checks), AMBER if checks else GREEN),
        ("ไม่สำเร็จ / Non-success", str(non_success), RED if non_success else GREEN),
        ("Warning / Error", f"{warnings} / {errors}", RED if errors else AMBER if warnings else GREEN),
    ]
    data = []
    for label, value, color in tiles:
        value_style = ParagraphStyle(
            f"TileValue{label}", parent=styles["tile_value"], textColor=color
        )
        data.append([p(label, styles["tile_label"]), p(value, value_style)])
    table = Table([data], colWidths=[151] * len(data), rowHeights=[42])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def status_row_background(row: dict[str, str]):
    if row["Status"] != "Successful":
        return RED_BG
    if row["Audit Status"] == "Check":
        return AMBER_BG
    return colors.white


def overview_table(rows: list[dict[str, str]], styles):
    headers = ["No.", "Group", "Backup Task", "Status", "Source", "Start", "End", "Duration", "Size", "Audit"]
    data = [[p(h, styles["table_header"]) for h in headers]]
    for row in rows:
        data.append([
            p(row["No."], styles["small_center"]),
            p(row["Group"], styles["small"]),
            p(row["Backup Task"], styles["small"]),
            p(row["Status"], styles["small_center"]),
            p(row["Source"], styles["small_center"]),
            p(time_only(row["Start"]), styles["small_center"]),
            p(time_only(row["End"]), styles["small_center"]),
            p(row["Duration"], styles["small_center"]),
            p(row["Size"], styles["small_right"]),
            p(row["Audit Status"], styles["small_center"]),
        ])
    widths = [22, 55, 213, 55, 76, 58, 58, 50, 58, 46]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
    ]
    for idx, row in enumerate(rows, start=1):
        commands.append(("BACKGROUND", (0, idx), (-1, idx), status_row_background(row)))
        if row["Status"] != "Successful":
            commands.append(("TEXTCOLOR", (3, idx), (3, idx), RED))
        elif row["Audit Status"] == "Check":
            commands.append(("TEXTCOLOR", (9, idx), (9, idx), AMBER))
    table.setStyle(TableStyle(commands))
    return table


def audit_table(rows: list[dict[str, str]], styles):
    headers = ["No.", "Backup Task", "File Count", "W / E", "Unchanged", "Size", "Same Size", "Audit Window", "Result", "Note"]
    data = [[p(h, styles["table_header"]) for h in headers]]
    for row in rows:
        data.append([
            p(row["No."], styles["small_center"]),
            p(row["Backup Task"], styles["small"]),
            p(row["File Count"], styles["small_right"]),
            p(row["Warning/Error"], styles["small_center"]),
            p(row["Unchanged"], styles["small_right"]),
            p(row["Size"], styles["small_right"]),
            p(row["Same Size"], styles["small_center"]),
            p(row["Audit Same Size"], styles["small_center"]),
            p(row["Audit Status"], styles["small_center"]),
            p(row["Note"], styles["small"]),
        ])
    widths = [22, 214, 55, 46, 65, 59, 52, 65, 48, 145]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
    ]
    for idx, row in enumerate(rows, start=1):
        commands.append(("BACKGROUND", (0, idx), (-1, idx), status_row_background(row)))
        if row["Audit Status"] == "Check":
            commands.append(("TEXTCOLOR", (8, idx), (8, idx), AMBER))
    table.setStyle(TableStyle(commands))
    return table


def exception_detail_elements(
    row: dict[str, str],
    report_date,
    index: int,
    total: int,
    styles,
    history_dir: Path | None = None,
):
    history_days = str(row.get("Audit Same Size") or "").split(" of ")[-1] or "7"
    history = row.get("_history") or load_task_history(
        row["Backup Task"], report_date, days=int(history_days or 7), history_dir=history_dir
    )
    status_color = RED if row["Status"] != "Successful" else AMBER
    banner_text = (
        "งานสำรองข้อมูลไม่สำเร็จ - ต้องตรวจสอบทันที"
        if row["Status"] != "Successful"
        else "งานสำรองข้อมูลสำเร็จ แต่ผล Audit ต้องได้รับการตรวจสอบ"
    )
    banner_style = ParagraphStyle(
        f"ExceptionBanner{index}",
        parent=styles["body"],
        fontName="Tahoma-Bold",
        fontSize=10,
        leading=13,
        textColor=status_color,
        alignment=TA_CENTER,
    )
    banner = Table(
        [[p(banner_text, banner_style)]],
        colWidths=[755],
        rowHeights=[30],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), RED_BG if row["Status"] != "Successful" else AMBER_BG),
        ("BOX", (0, 0), (-1, -1), 0.7, status_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    event_description = (
        f"The backup task {row['Backup Task']} was completed successfully."
        if row["Status"] == "Successful"
        else f"The backup task {row['Backup Task']} ended with status {row['Status']}."
    )
    detail_rows = [
        ("Status", row["Status"], "Audit Status", row["Audit Status"]),
        ("Source", row["Source"], "Group", row["Group"]),
        ("Execution time", short_dt(row["Start"]), "Completed", short_dt(row["End"])),
        ("Duration", row["Duration"], "Transferred size", row["Size"]),
        ("Processed file count", row["File Count"], "Unchanged", row["Unchanged"]),
        ("Warning / Error", row["Warning/Error"], "Audit window", row["Audit Same Size"]),
        ("Destination", "Not returned by current Web API", "Finding", row["Note"]),
        ("Event time", short_dt(row["End"]), "Summary event", event_description),
    ]
    details = []
    for left_label, left_value, right_label, right_value in detail_rows:
        details.append([
            p(left_label, styles["table_header"]),
            p(left_value, styles["body"]),
            p(right_label, styles["table_header"]),
            p(right_value, styles["body"]),
        ])
    detail_table = Table(details, colWidths=[100, 250, 100, 305], hAlign="LEFT")
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY),
        ("BACKGROUND", (2, 0), (2, -1), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    hist_headers = [
        "Date", "Status", "Start", "End", "Duration", "Size",
        "File Count", "Unchanged", "Audit Window", "Result",
    ]
    hist_data = [[p(value, styles["table_header"]) for value in hist_headers]]
    for item in history:
        hist_data.append([
            p(datetime.strptime(item["Report Date"], "%Y-%m-%d").strftime("%d/%m/%Y"), styles["small_center"]),
            p(item["Status"], styles["small_center"]),
            p(time_only(item["Start"]), styles["small_center"]),
            p(time_only(item["End"]), styles["small_center"]),
            p(item["Duration"], styles["small_center"]),
            p(item["Size"], styles["small_right"]),
            p(item["File Count"], styles["small_right"]),
            p(item["Unchanged"], styles["small_right"]),
            p(item["Audit Same Size"], styles["small_center"]),
            p(item["Audit Status"], styles["small_center"]),
        ])
    history_table = Table(
        hist_data,
        colWidths=[66, 72, 58, 58, 58, 65, 65, 69, 76, 60],
        repeatRows=1,
        hAlign="LEFT",
    )
    history_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for hist_index, item in enumerate(history, start=1):
        if item["Audit Status"] == "Check":
            history_commands.append(("BACKGROUND", (0, hist_index), (-1, hist_index), AMBER_BG))
    history_table.setStyle(TableStyle(history_commands))

    if row["Status"] == "Successful" and row["Size"] in {"0 Bytes", "0.00 KB", "0 KB"}:
        analysis_text = (
            "งานสำรองข้อมูลทำงานสำเร็จและไม่พบ Warning/Error แต่ไม่มีข้อมูลถูกถ่ายโอน "
            f"โดยจำนวนไฟล์ {row['File Count']} รายการและค่า Unchanged {row['Unchanged']} "
            f"คงเดิมจนถึงเกณฑ์ {row['Audit Same Size']} จึงควรตรวจสอบข้อมูลต้นทางและขอบเขตของ Backup Task"
        )
    else:
        analysis_text = row["Note"]

    rec_data = [
        [p("1", styles["small_center"]), p("ตรวจสอบว่าข้อมูลต้นทางมีการเปลี่ยนแปลงตามที่คาดหวังหรือไม่", styles["body"])],
        [p("2", styles["small_center"]), p("ตรวจสอบ Source Folder และขอบเขตของ Backup Task ว่าถูกต้อง", styles["body"])],
        [p("3", styles["small_center"]), p("หากไม่มีข้อมูลใหม่โดยตั้งใจ ให้บันทึกเหตุผลเพื่อปิดรายการตรวจสอบ", styles["body"])],
    ]
    rec_table = Table(rec_data, colWidths=[28, 727], hAlign="LEFT")
    rec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return [
        p("รายละเอียดงานที่ต้องตรวจสอบ / Attention Task Detail", styles["title"]),
        p(
            f"Task {index} of {total} | Report date: {report_date.strftime('%d/%m/%Y')} | Backup Task: {row['Backup Task']}",
            styles["subtitle"],
        ),
        Spacer(1, 7),
        banner,
        Spacer(1, 8),
        p("ข้อมูลการทำงานล่าสุด / Latest Execution", styles["section"]),
        detail_table,
        Spacer(1, 8),
        p(f"ประวัติย้อนหลัง {history_days} วัน / {history_days}-Day History", styles["section"]),
        history_table,
        Spacer(1, 8),
        p("ผลการตรวจสอบอัตโนมัติ / Automated Finding", styles["section"]),
        p(analysis_text, styles["body"]),
        Spacer(1, 7),
        p("รายการตรวจสอบที่แนะนำ / Recommended Checks", styles["section"]),
        rec_table,
        Spacer(1, 5),
        p(
            "Destination and package-level log descriptions are not returned by the current Web API calls. "
            "This page reports only fields verified directly from the NAS APIs.",
            styles["note"],
        ),
    ]


def cloud_sync_elements(audit: dict[str, object], styles):
    cloud = audit.get("cloud_sync") or {}
    site_label = str(cloud.get("site_label") or "Yard - Cloud Sync")
    status = str(cloud.get("tray_status") or "unknown")
    connection_count = int(cloud.get("connection_count") or 0)
    paused = bool(cloud.get("paused", False))
    connections = list(cloud.get("connections") or [])
    logs = list(cloud.get("logs") or [])

    summary = Table(
        [
            [p("Site", styles["table_header"]), p(site_label, styles["body"]),
             p("Cloud Sync status", styles["table_header"]), p(status, styles["body"])],
            [p("Connections", styles["table_header"]), p(connection_count, styles["body"]),
             p("Paused", styles["table_header"]), p("Yes" if paused else "No", styles["body"])],
        ],
        colWidths=[105, 272, 105, 273],
        hAlign="LEFT",
    )
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY),
        ("BACKGROUND", (2, 0), (2, -1), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements = [
        p("รายงานไซต์ Yard / Yard Cloud Sync Report", styles["title"]),
        p(
            "ข้อมูลจาก Cloud Sync Web API และ Log Center ของ NAS ปลายทางโดยตรง",
            styles["subtitle"],
        ),
        Spacer(1, 7),
        summary,
        Spacer(1, 8),
        p("รายการเชื่อมต่อ / Connections", styles["section"]),
    ]

    if connections:
        conn_data = [[p(value, styles["table_header"]) for value in
                      ("Name", "Provider", "Local path", "Remote path", "Status")]]
        for item in connections:
            conn_data.append([
                p(item.get("name", "-"), styles["small"]),
                p(item.get("provider", "-"), styles["small_center"]),
                p(item.get("local_path", "-"), styles["small"]),
                p(item.get("remote_path", "-"), styles["small"]),
                p(item.get("status", "unknown"), styles["small_center"]),
            ])
        connection_table = Table(conn_data, colWidths=[150, 90, 205, 205, 105], repeatRows=1, hAlign="LEFT")
        connection_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("GRID", (0, 0), (-1, -1), 0.35, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.extend([connection_table, Spacer(1, 8)])
    else:
        no_connections = Table(
            [[p(
                "Cloud Sync Web API ไม่ส่งรายการ connection กลับมา โปรดตรวจสอบว่า Site นี้มีงาน Cloud Sync ที่เปิดใช้งานและบัญชีรายงานมีสิทธิ์อ่านข้อมูล",
                styles["body"],
            )]],
            colWidths=[755],
        )
        no_connections.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AMBER_BG),
            ("BOX", (0, 0), (-1, -1), 0.6, AMBER),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.extend([no_connections, Spacer(1, 8)])

    elements.append(p("เหตุการณ์ Cloud Sync ล่าสุด / Recent Cloud Sync Events", styles["section"]))
    if logs:
        log_data = [[p(value, styles["table_header"]) for value in ("Time", "Level", "Message")]]
        for item in logs[:20]:
            log_data.append([
                p(item.get("time", "-"), styles["small_center"]),
                p(item.get("level", "-"), styles["small_center"]),
                p(item.get("message", "-"), styles["small"]),
            ])
        log_table = Table(log_data, colWidths=[120, 80, 555], repeatRows=1, hAlign="LEFT")
        log_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.35, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(log_table)
    else:
        elements.append(p(
            "ไม่พบเหตุการณ์ Cloud Sync จาก Log Center ที่ Web API ส่งกลับมาในรอบการอ่านครั้งนี้",
            styles["note"],
        ))
    methods = ", ".join(cloud.get("api_methods") or []) or "none"
    elements.extend([Spacer(1, 6), p(f"Successful API methods: {methods}", styles["note"])])
    return elements


def page_header(canvas, logo_path: Path):
    page_width, page_height = landscape(A4)
    canvas.saveState()
    canvas.drawImage(
        str(logo_path),
        10 * mm,
        page_height - 16.5 * mm,
        width=15 * mm,
        height=12 * mm,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )
    canvas.setFillColor(NAVY)
    canvas.setFont("Tahoma-Bold", 11)
    canvas.drawString(29 * mm, page_height - 9.5 * mm, "Pylon Backup Report")
    canvas.setFillColor(MUTED)
    canvas.setFont("Tahoma", 6.5)
    canvas.drawString(
        29 * mm,
        page_height - 14 * mm,
        "PYLON IT OPERATIONS - Automated Backup Reporting",
    )
    canvas.setStrokeColor(BLUE)
    canvas.setLineWidth(0.8)
    canvas.line(10 * mm, page_height - 19 * mm, page_width - 10 * mm, page_height - 19 * mm)
    canvas.restoreState()


def page_footer(canvas, doc, server_name: str = "BACKUP-SERVER"):
    canvas.saveState()
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.4)
    canvas.line(10 * mm, 10 * mm, landscape(A4)[0] - 10 * mm, 10 * mm)
    canvas.setFont("Tahoma", 6.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(10 * mm, 6.2 * mm, f"Daily Backup Health Report - {server_name}")
    canvas.drawRightString(
        landscape(A4)[0] - 10 * mm,
        6.2 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def build_pdf(
    output_path: Path,
    rows: list[dict[str, str]],
    audit: dict[str, object],
    server_name: str = "BACKUP-SERVER",
    history_dir: Path | None = None,
    sangfor_capture_path: Path | None = None,
    logo_path: Path | None = None,
):
    regular_font = os.environ.get("BACKUP_REPORT_FONT_REGULAR", r"C:\Windows\Fonts\tahoma.ttf")
    bold_font = os.environ.get("BACKUP_REPORT_FONT_BOLD", r"C:\Windows\Fonts\tahomabd.ttf")
    if not Path(regular_font).is_file() or not Path(bold_font).is_file():
        raise ValueError("Thai report fonts are missing; check BACKUP_REPORT_FONT_REGULAR and BACKUP_REPORT_FONT_BOLD")
    pdfmetrics.registerFont(TTFont("Tahoma", regular_font))
    pdfmetrics.registerFont(TTFont("Tahoma-Bold", bold_font))
    report_logo = Path(logo_path) if logo_path is not None else DEFAULT_LOGO_PATH
    if not report_logo.is_file():
        raise ValueError(f"Report logo not found: {report_logo}")
    styles = make_styles()
    now = datetime.now(timezone(timedelta(hours=7), "Asia/Bangkok"))
    report_date = audit["report_date"]

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=25 * mm,
        bottomMargin=14 * mm,
        title=f"Daily Backup Health Report {report_date.isoformat()}",
        author="Pylon Backup Report",
        subject="Active Backup for Business daily status",
    )

    story = [
        p("รายงานสถานะการสำรองข้อมูลประจำวัน", styles["title"]),
        p(
            f"Daily Backup Health Report | Server: {server_name} | Data date: {report_date.strftime('%d/%m/%Y')} | Generated: {now.strftime('%d/%m/%Y %H:%M:%S')} (Asia/Bangkok)",
            styles["subtitle"],
        ),
        Spacer(1, 6),
        summary_tiles(rows, audit, styles),
        Spacer(1, 7),
    ]

    attention = [r for r in rows if r["Audit Status"] == "Check" or r["Status"] != "Successful"]
    story.append(p("รายการที่ต้องตรวจสอบ / Attention Required", styles["section"]))
    if attention:
        att_data = [[
            p("Backup Task", styles["table_header"]),
            p("Status", styles["table_header"]),
            p("Audit", styles["table_header"]),
            p("Finding", styles["table_header"]),
        ]]
        for row in attention:
            att_data.append([
                p(row["Backup Task"], styles["small"]),
                p(row["Status"], styles["small_center"]),
                p(row["Audit Status"], styles["small_center"]),
                p(row["Note"], styles["small"]),
            ])
        att = Table(att_data, colWidths=[260, 80, 70, 345], repeatRows=1)
        att.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AMBER),
            ("BACKGROUND", (0, 1), (-1, -1), AMBER_BG),
            ("GRID", (0, 0), (-1, -1), 0.4, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([att, Spacer(1, 7)])
    else:
        story.extend([p("ไม่พบรายการที่ต้องตรวจสอบ / No attention items found.", styles["body"]), Spacer(1, 7)])

    story.extend([
        p("ภาพรวมงานสำรองข้อมูล / Backup Overview", styles["section"]),
        overview_table(rows, styles),
        PageBreak(),
        p("รายละเอียดข้อมูลและการตรวจสอบ / Data Integrity and Audit Details", styles["title"]),
        p(
            f"Direct API collection: {audit['row_count']} Active Backup results normalized and verified before PDF generation.",
            styles["subtitle"],
        ),
        Spacer(1, 7),
        audit_table(rows, styles),
        Spacer(1, 8),
        KeepTogether([
            p("หมายเหตุการตีความ / Interpretation Notes", styles["section"]),
            p(
                "1. Check is reported only when the Active Backup API returns Warning, Failed, warning_count or error_count. "
                "2. Same Size and History Window are supporting information and do not change a Successful NAS status to Check. "
                "3. The PDF generator stops when either NAS API cannot be read or no daily Active Backup results are available.",
                styles["note"],
            ),
            Spacer(1, 5),
            p(
                f"Data sources: {Path(audit['result_path']).name} and {Path(audit['raw_path']).name}. Cloud Sync connections: {audit.get('cloud_sync', {}).get('connection_count', 'N/A')}; status: {audit.get('cloud_sync', {}).get('tray_status', 'N/A')}.",
                styles["note"],
            ),
        ]),
    ])
    story.append(PageBreak())
    story.extend(cloud_sync_elements(audit, styles))
    if attention:
        for exception_index, exception_row in enumerate(attention, start=1):
            story.append(PageBreak())
            story.extend(
                exception_detail_elements(
                    exception_row,
                    report_date,
                    exception_index,
                    len(attention),
                    styles,
                    history_dir=history_dir,
                )
            )
    if sangfor_capture_path is not None:
        capture_path = Path(sangfor_capture_path)
        if not capture_path.is_file():
            raise ValueError(f"Sangfor capture not found: {capture_path}")
        capture_width = 260 * mm
        capture_height = capture_width * 1080 / 1920
        capture_image = Image(str(capture_path), width=capture_width, height=capture_height)
        capture_image.hAlign = "CENTER"
        story.extend([
            PageBreak(),
            p("ภาพสถานะการสำรองข้อมูล Sangfor aCloud / Sangfor Backup Evidence", styles["title"]),
            p(
                f"Captured automatically from the Sangfor VM Backup console | Generated: {now.strftime('%d/%m/%Y %H:%M:%S')} (Asia/Bangkok)",
                styles["subtitle"],
            ),
            Spacer(1, 6),
            capture_image,
        ])
    def header_footer(canvas, current_doc):
        page_header(canvas, report_logo)
        page_footer(canvas, current_doc, server_name=server_name)

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def main():
    parser = argparse.ArgumentParser(description="Build a backup PDF from normalized CSV files")
    parser.add_argument("--result-csv", required=True, type=Path)
    parser.add_argument("--raw-csv", required=True, type=Path)
    parser.add_argument("--server-name", default="BACKUP-SERVER")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result_fields, result_rows = read_csv(args.result_csv)
    raw_fields, raw_rows = read_csv(args.raw_csv)
    audit = validate_and_reconcile(
        result_fields,
        result_rows,
        raw_fields,
        raw_rows,
        result_path=args.result_csv,
        raw_path=args.raw_csv,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = args.output or OUTPUT_DIR / f"Backup_Report_{audit['report_date'].isoformat()}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(
        output,
        result_rows,
        audit,
        server_name=args.server_name,
        history_dir=args.result_csv.parent,
    )
    print(output)
    print(f"rows={audit['row_count']} warnings={audit['warning_total']} errors={audit['error_total']}")


if __name__ == "__main__":
    main()
