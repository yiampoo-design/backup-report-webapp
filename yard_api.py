from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from synology_api import SynologyApiError, SynologyClient


BANGKOK = timezone(timedelta(hours=7), name="Asia/Bangkok")
CONNECTION_API = "SYNO.SynologyDriveShareSync.Connection"
SESSION_API = "SYNO.SynologyDriveShareSync.Session"


def _first(item: dict[str, Any], *keys: str, default: Any = "-") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return default


def _items(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("conn", "connections", "session", "sessions", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _status(value: Any) -> str:
    raw = str(value or "unknown").strip().lower()
    labels = {
        "uptodate": "Up to date",
        "syncing": "Syncing",
        "connecting": "Connecting",
        "pause": "Paused",
        "stop": "Stopped",
        "unlink": "Unlinked",
    }
    return labels.get(raw, str(value or "Unknown"))


def _direction(value: Any) -> str:
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


def _time(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return str(value or "-")
    return datetime.fromtimestamp(numeric, BANGKOK).strftime("%Y-%m-%d %H:%M:%S")


def collect_drive_sharesync(config: dict, password: str) -> dict[str, Any]:
    """Read Yard Drive ShareSync only. This module must never access primary NAS."""
    client = SynologyClient(
        str(config.get("url") or ""),
        verify_ssl=bool(config.get("verify_ssl", True)),
    )
    try:
        client.login(str(config.get("username") or ""), password)
        definitions = client.discover([CONNECTION_API, SESSION_API])
        missing = [name for name in (CONNECTION_API, SESSION_API) if name not in definitions]
        if missing:
            raise SynologyApiError("Drive ShareSync API is not available: " + ", ".join(missing))

        connection_data = client.call(CONNECTION_API, "list", version=1)
        raw_connections = _items(connection_data)
        folders: list[dict[str, str]] = []
        logs: list[dict[str, str]] = []
        errors: dict[str, str] = {}
        methods = [f"{CONNECTION_API}.list"]

        for connection in raw_connections:
            connection_id = _first(connection, "id", "conn_id", default="")
            if connection_id == "":
                continue
            try:
                session_data = client.call(
                    SESSION_API,
                    "list",
                    {"conn_id": connection_id, "offset": 0, "limit": 1024},
                    version=1,
                )
                methods.append(f"{SESSION_API}.list")
            except SynologyApiError as exc:
                errors[f"session_{connection_id}"] = str(exc)
                continue
            for session in _items(session_data):
                enabled = bool(_first(session, "enable", "enabled", default=True))
                raw_status = _first(session, "status", "db_status", default="unknown")
                folders.append({
                    "name": str(_first(session, "remote_share", "local_share")),
                    "local_path": str(_first(session, "local_share")),
                    "remote_path": str(_first(session, "remote_share")),
                    "sync_direction": _direction(_first(session, "sync_direction", default="0")),
                    "status": _status(raw_status),
                    "raw_status": str(raw_status),
                    "enabled": "Yes" if enabled else "No",
                })

        try:
            history = client.call(
                SESSION_API,
                "list_sync_history",
                {"offset": 0, "limit": 200, "sess_id": 0},
                version=1,
            )
            methods.append(f"{SESSION_API}.list_sync_history")
            for item in history.get("history_items", []):
                if not isinstance(item, dict):
                    continue
                action = str(_first(item, "action")).replace("_", " ").title()
                path = str(_first(item, "path"))
                normalized = path.replace("\\", "/").rstrip("/")
                raw_type = str(_first(item, "item_type", "file_type", "type", default="")).lower()
                is_dir = str(_first(item, "is_dir", "is_folder", default="")).lower()
                item_type = "Folder" if is_dir in {"1", "true", "yes"} or raw_type in {"1", "folder", "dir"} else "File"
                logs.append({
                    "time": _time(_first(item, "time", default="")),
                    "name": normalized.rsplit("/", 1)[-1] if normalized else path,
                    "event": action,
                    "level": action,
                    "item_type": item_type,
                    "path": path,
                })
        except SynologyApiError as exc:
            errors["sync_history"] = str(exc)

        folders.sort(key=lambda item: item["local_path"].casefold())
        logs.sort(key=lambda item: item["time"], reverse=True)
        enabled = [item for item in folders if item["enabled"] == "Yes"]
        up_to_date = sum(1 for item in enabled if item["raw_status"].casefold() == "uptodate")
        return {
            "source_type": "drive_sharesync",
            "source_label": "Synology Drive ShareSync Web API",
            "connection_count": len(enabled),
            "storage_connection_count": len(raw_connections),
            "up_to_date_count": up_to_date,
            "healthy": bool(enabled) and up_to_date == len(enabled),
            "paused": any(item["raw_status"].casefold() in {"pause", "stop"} for item in enabled),
            "connections": folders,
            "logs": logs[:50],
            "api_methods": sorted(set(methods)),
            "api_errors": errors,
            "api_connected": True,
            "has_connections": bool(enabled),
        }
    finally:
        client.logout()
