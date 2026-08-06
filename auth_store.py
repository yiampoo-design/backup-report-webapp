from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path


PBKDF2_ITERATIONS = 310_000


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


class AuthStore:
    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def initialize(self, username: str, password: str) -> None:
        if self.exists():
            return
        if not username or not password or password == "CHANGE_THIS_PASSWORD":
            raise RuntimeError("Set BACKUP_REPORT_WEB_USERNAME and BACKUP_REPORT_WEB_PASSWORD for the initial web login")
        self.set_password(username, password)

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError(f"Cannot read web authentication data: {exc}") from exc

    def username(self) -> str:
        return str(self._load().get("username") or "")

    def verify(self, username: str, password: str) -> bool:
        try:
            saved = self._load()
            if not hmac.compare_digest(str(saved.get("username") or ""), username):
                return False
            salt = _decode(saved["salt"])
            expected = _decode(saved["password_hash"])
            actual = _derive(password, salt, int(saved["iterations"]))
            return hmac.compare_digest(actual, expected)
        except (KeyError, ValueError, TypeError, RuntimeError):
            return False

    def set_password(self, username: str, password: str) -> None:
        if len(password) < 8:
            raise ValueError("รหัสผ่านใหม่ต้องมีอย่างน้อย 8 ตัวอักษร")
        salt = os.urandom(16)
        record = {
            "version": 1,
            "username": username,
            "algorithm": "pbkdf2_sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": _encode(salt),
            "password_hash": _encode(_derive(password, salt, PBKDF2_ITERATIONS)),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            os.chmod(temp, 0o640)
        temp.replace(self.path)
