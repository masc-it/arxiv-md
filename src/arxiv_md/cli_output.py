from __future__ import annotations

import json
import sys
from typing import Any


def emit(payload: dict[str, Any], stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    json.dump(payload, stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def emit_ok(payload: dict[str, Any], stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    emit({"ok": True, **payload}, stream=stream)


def emit_error(
    message: str,
    *,
    code: str = "convert_error",
    stream: Any = None,
    **extra: Any,
) -> None:

    if stream is None:
        stream = sys.stderr
    error_obj: dict[str, Any] = {"code": code, "message": message, **extra}
    emit({"ok": False, "error": error_obj}, stream=stream)
