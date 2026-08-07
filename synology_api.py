from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class SynologyApiError(RuntimeError):
    pass


ERROR_MESSAGES = {
    100: "Unknown error",
    101: "Invalid parameter",
    102: "Requested API does not exist",
    103: "Requested method does not exist",
    104: "Requested version is not supported",
    105: "Insufficient user privilege",
    106: "Session timeout",
    107: "Session interrupted",
    400: "Invalid account or password",
    401: "Account disabled",
    402: "Permission denied",
    403: "Two-step verification required",
    404: "Two-step verification failed",
    406: "Enforce two-step verification",
    407: "Blocked IP",
    408: "Expired password",
    409: "Password must be changed",
}


@dataclass
class ApiDefinition:
    name: str
    path: str
    min_version: int
    max_version: int
    request_format: str = ""


class SynologyClient:
    def __init__(self, base_url: str, verify_ssl: bool = True, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.sid = ""
        self.syno_token = ""
        self.api_info: dict[str, ApiDefinition] = {}

    def _context(self):
        if self.base_url.lower().startswith("https://") and not self.verify_ssl:
            return ssl._create_unverified_context()
        return ssl.create_default_context()

    def _request(self, path: str, params: dict[str, Any], post: bool = False) -> dict[str, Any]:
        url = f"{self.base_url}/webapi/{path.lstrip('/')}"
        encoded = urllib.parse.urlencode(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list, bool))
                else value
                for key, value in params.items()
                if value is not None
            }
        )
        data = encoded.encode("utf-8") if post else None
        if not post:
            url = f"{url}?{encoded}"
        request = urllib.request.Request(url, data=data)
        if post:
            request.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        try:
            with urllib.request.urlopen(
                request, context=self._context(), timeout=self.timeout
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SynologyApiError(f"HTTP {exc.code} from {self.base_url}") from exc
        except urllib.error.URLError as exc:
            raise SynologyApiError(f"Cannot connect to {self.base_url}: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SynologyApiError(f"Invalid JSON response from {self.base_url}") from exc
        return payload

    def discover(self, names: list[str] | None = None) -> dict[str, ApiDefinition]:
        query = ",".join(names) if names else "all"
        payload = self._request(
            "query.cgi",
            {"api": "SYNO.API.Info", "version": 1, "method": "query", "query": query},
        )
        self._require_success(payload, "API discovery")
        definitions: dict[str, ApiDefinition] = {}
        for name, value in payload.get("data", {}).items():
            definitions[name] = ApiDefinition(
                name=name,
                path=value.get("path", "entry.cgi"),
                min_version=int(value.get("minVersion", 1)),
                max_version=int(value.get("maxVersion", 1)),
                request_format=value.get("requestFormat", ""),
            )
        self.api_info.update(definitions)
        return definitions

    def login(self, username: str, password: str) -> None:
        auth = self.discover(["SYNO.API.Auth"]).get("SYNO.API.Auth")
        if not auth:
            raise SynologyApiError("SYNO.API.Auth is not available")
        payload = self._request(
            auth.path,
            {
                "api": auth.name,
                "version": auth.max_version,
                "method": "login",
                "account": username,
                "passwd": password,
                "session": "BackupReportPortable",
                "format": "sid",
            },
            post=True,
        )
        self._require_success(payload, "Login")
        data = payload.get("data", {})
        self.sid = data.get("sid", "")
        self.syno_token = data.get("synotoken", "")
        if not self.sid:
            raise SynologyApiError("Login succeeded but DSM did not return a session ID")

    def call(
        self,
        api: str,
        method: str,
        params: dict[str, Any] | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        if not self.sid:
            raise SynologyApiError("Not logged in")
        definition = self.api_info.get(api)
        if not definition:
            definition = self.discover([api]).get(api)
        if not definition:
            raise SynologyApiError(f"API is not available: {api}")
        request_params: dict[str, Any] = {
            "api": api,
            "version": version or definition.max_version,
            "method": method,
            "_sid": self.sid,
        }
        if self.syno_token:
            request_params["SynoToken"] = self.syno_token
        # Synology's package UI sends method arguments as ordinary top-level
        # form fields. Dict/list values are JSON-encoded by `_request`.
        request_params.update(params or {})
        payload = self._request(definition.path, request_params, post=True)
        self._require_success(payload, f"{api}.{method}")
        return payload.get("data", {})

    def logout(self) -> None:
        if not self.sid:
            return
        try:
            auth = self.api_info.get("SYNO.API.Auth") or self.discover(
                ["SYNO.API.Auth"]
            ).get("SYNO.API.Auth")
            if auth:
                self._request(
                    auth.path,
                    {
                        "api": auth.name,
                        "version": auth.max_version,
                        "method": "logout",
                        "session": "BackupReportPortable",
                        "_sid": self.sid,
                        "SynoToken": self.syno_token,
                    },
                    post=True,
                )
        finally:
            self.sid = ""
            self.syno_token = ""

    @staticmethod
    def _require_success(payload: dict[str, Any], action: str) -> None:
        if payload.get("success") is True:
            return
        code = int(payload.get("error", {}).get("code", 0))
        message = ERROR_MESSAGES.get(code, f"DSM error {code}")
        raise SynologyApiError(f"{action}: {message}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.logout()


READ_ONLY_PROBES = {
    "active_backup": {
        "apis": [
            "SYNO.ActiveBackup.Task",
            "SYNO.ActiveBackup.Log",
            "SYNO.ActiveBackup.Overview",
            "SYNO.ActiveBackup.Report",
            "SYNO.ActiveBackup.ReportGet",
        ],
        "methods": ["list", "get"],
    },
    "cloud_sync": {
        "apis": [
            "SYNO.SynologyDriveShareSync.Connection",
            "SYNO.SynologyDriveShareSync.Session",
        ],
        "methods": ["list", "get", "list_syncfolder", "list_sync_history"],
    },
}


def probe_read_only(
    client: SynologyClient, profile: str
) -> dict[str, Any]:
    """Try only conventional read methods; errors are retained for API mapping."""
    spec = READ_ONLY_PROBES[profile]
    definitions = client.discover(spec["apis"])
    result: dict[str, Any] = {
        "profile": profile,
        "available": {
            name: {
                "path": value.path,
                "min_version": value.min_version,
                "max_version": value.max_version,
                "request_format": value.request_format,
            }
            for name, value in definitions.items()
        },
        "calls": [],
    }
    for api in spec["apis"]:
        if api not in definitions:
            continue
        for method in spec["methods"]:
            try:
                data = client.call(api, method, version=1 if profile == "active_backup" else None)
                result["calls"].append(
                    {"api": api, "method": method, "success": True, "data": data}
                )
            except SynologyApiError as exc:
                result["calls"].append(
                    {"api": api, "method": method, "success": False, "error": str(exc)}
                )
    return result
