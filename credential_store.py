from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


CRYPTPROTECT_UI_FORBIDDEN = 0x01
DESCRIPTION = "Backup Report Portable"


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return (
        DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
        buffer,
    )


def protect_text(value: str) -> str:
    """Protect with Windows DPAPI; Linux relies on a permission-restricted data file."""
    if not value:
        return ""
    if os.name != "nt":
        return "linux:" + base64.b64encode(value.encode("utf-8")).decode("ascii")
    source, source_buffer = _blob(value.encode("utf-8"))
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        DESCRIPTION,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(output.pbData, output.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer


def unprotect_text(value: str) -> str:
    """Decrypt DPAPI or decode the Linux permission-protected representation."""
    if not value:
        return ""
    if value.startswith("linux:"):
        return base64.b64decode(value.removeprefix("linux:")).decode("utf-8")
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI credentials cannot be read on Linux; enter the NAS passwords again")
    raw = base64.b64decode(value)
    source, source_buffer = _blob(raw)
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer
