from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import logging
import os
import threading
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from .logger import get_logger

logger = get_logger("legal_agent.performance")

SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "content",
    "context",
    "description",
    "document",
    "draft",
    "evidence",
    "fact",
    "key",
    "message",
    "notes",
    "password",
    "payload",
    "prompt",
    "query",
    "secret",
    "text",
    "token",
}
DEFAULT_SLOW_DB_MS = 200.0
DEFAULT_SLOW_AI_MS = 15_000.0
DEFAULT_SLOW_STARTUP_MS = 3_000.0
DEFAULT_EXCESSIVE_DB_CONNECTIONS = 75

_active_scope: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "legal_agent_performance_scope",
    default=None,
)
_lock = threading.Lock()
_db_connection_counts: Counter[str] = Counter()
_db_init_attempts: Counter[str] = Counter()
_db_repeated_init_warned: set[str] = set()
_openai_client_creations = 0


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _safe_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        if isinstance(value, str):
            return {"redacted": True, "chars": len(value)}
        if isinstance(value, (list, tuple, set, dict)):
            return {"redacted": True, "items": len(value)}
        return "<redacted>"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(child_key): _safe_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(key, item) for item in list(value)[:20]]
    if isinstance(value, str):
        return value if len(value) <= 160 else f"{value[:157]}..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def safe_context(context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not context:
        return {}
    return {str(key): _safe_value(str(key), value) for key, value in context.items()}


def _log_checkpoint(payload: dict[str, Any], *, level: int) -> None:
    logger.log(level, "performance_checkpoint %s", json.dumps(payload, sort_keys=True))


def _checkpoint_level(success: bool, duration_ms: float, slow_ms: float | None, requested_level: int) -> int:
    if not success:
        return logging.WARNING
    if slow_ms is not None and duration_ms >= slow_ms:
        return logging.WARNING
    return requested_level


@contextlib.contextmanager
def performance_checkpoint(
    operation: str,
    *,
    context: Mapping[str, Any] | None = None,
    slow_ms: float | None = None,
    log_success: bool = True,
    level: int = logging.INFO,
) -> Iterator[dict[str, Any]]:
    start = time.perf_counter()
    scope = {
        "operation": operation,
        "db_connections": 0,
        "db_initializations": 0,
        "openai_client_creations": 0,
        "warned": set(),
    }
    parent_scope = _active_scope.get()
    token = _active_scope.set(scope)
    success = False
    exception_type = ""
    try:
        yield scope
        success = True
    except Exception as exc:
        exception_type = type(exc).__name__
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        _active_scope.reset(token)
        if parent_scope is not None:
            parent_scope["db_connections"] += scope["db_connections"]
            parent_scope["db_initializations"] += scope["db_initializations"]
            parent_scope["openai_client_creations"] += scope["openai_client_creations"]
        payload = {
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
            "context": safe_context(context),
        }
        if exception_type:
            payload["exception_type"] = exception_type
        if scope["db_connections"]:
            payload["db_connections"] = scope["db_connections"]
        if scope["db_initializations"]:
            payload["db_initializations"] = scope["db_initializations"]
        if scope["openai_client_creations"]:
            payload["openai_client_creations"] = scope["openai_client_creations"]
        log_level = _checkpoint_level(success, duration_ms, slow_ms, level)
        if log_success or not success or log_level >= logging.WARNING:
            _log_checkpoint(payload, level=log_level)


def summarize_path(path: str | Path) -> str:
    path_text = str(path)
    digest = hashlib.sha256(path_text.encode("utf-8")).hexdigest()[:10]
    return f"{Path(path_text).name}:{digest}"


def record_db_connection(path: str | Path, duration_ms: float, *, success: bool = True, exception_type: str = "") -> None:
    key = summarize_path(path)
    with _lock:
        _db_connection_counts[key] += 1
        count = _db_connection_counts[key]
    scope = _active_scope.get()
    if scope is not None:
        scope["db_connections"] += 1
        threshold = _env_int("LEGAL_AGENT_DB_CONNECTION_WARNING_THRESHOLD", DEFAULT_EXCESSIVE_DB_CONNECTIONS)
        if scope["db_connections"] > threshold and "db_connection_threshold" not in scope["warned"]:
            scope["warned"].add("db_connection_threshold")
            _log_checkpoint(
                {
                    "operation": "db_connection_threshold_exceeded",
                    "success": True,
                    "context": {
                        "active_operation": scope["operation"],
                        "db_connections": scope["db_connections"],
                        "threshold": threshold,
                    },
                },
                level=logging.WARNING,
            )

    slow_ms = _env_float("LEGAL_AGENT_SLOW_DB_CONNECTION_MS", DEFAULT_SLOW_DB_MS)
    should_log = _env_bool("LEGAL_AGENT_PERF_VERBOSE", False) or not success or duration_ms >= slow_ms
    if should_log:
        payload = {
            "operation": "database_connection_acquisition",
            "duration_ms": round(duration_ms, 3),
            "success": success,
            "context": {"db_path": key, "connection_count": count},
        }
        if exception_type:
            payload["exception_type"] = exception_type
        _log_checkpoint(payload, level=logging.WARNING if not success or duration_ms >= slow_ms else logging.DEBUG)
    elif count == 1 or count % _env_int("LEGAL_AGENT_DB_CONNECTION_SUMMARY_EVERY", 50) == 0:
        logger.debug(
            "db_connection_summary %s",
            json.dumps({"db_path": key, "connection_count": count}, sort_keys=True),
        )


def record_db_initialization(path: str | Path, *, skipped: bool = False) -> None:
    key = summarize_path(path)
    with _lock:
        _db_init_attempts[key] += 1
        count = _db_init_attempts[key]
        should_warn = count > 1 and key not in _db_repeated_init_warned
        if should_warn:
            _db_repeated_init_warned.add(key)
    scope = _active_scope.get()
    if scope is not None and not skipped:
        scope["db_initializations"] += 1
    if should_warn:
        _log_checkpoint(
            {
                "operation": "database_initialization_repeated",
                "success": True,
                "context": {
                    "db_path": key,
                    "attempt_count": count,
                    "skipped": skipped,
                    "improvement_hint": "A startup/service path requested init_db more than once for the same database in one process.",
                },
            },
            level=logging.WARNING,
        )


def record_openai_client_initialization(*, sdk: str, created: bool) -> None:
    global _openai_client_creations
    scope = _active_scope.get()
    if created:
        with _lock:
            _openai_client_creations += 1
            count = _openai_client_creations
        if scope is not None:
            scope["openai_client_creations"] += 1
        threshold = _env_int("LEGAL_AGENT_OPENAI_CLIENT_WARNING_THRESHOLD", 3)
        if count > threshold:
            _log_checkpoint(
                {
                    "operation": "openai_client_creation_repeated",
                    "success": True,
                    "context": {
                        "sdk": sdk,
                        "creation_count": count,
                        "threshold": threshold,
                        "improvement_hint": "OpenAI clients are being created repeatedly; confirm client caching is active.",
                    },
                },
                level=logging.WARNING,
            )
    elif _env_bool("LEGAL_AGENT_PERF_VERBOSE", False):
        logger.debug(
            "openai_client_cache_hit %s",
            json.dumps({"sdk": sdk, "creation_count": _openai_client_creations}, sort_keys=True),
        )
