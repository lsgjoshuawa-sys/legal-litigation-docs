from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db


SAFE_CHECK_JOB = (
    "Observe legal-agent-gui heartbeat and autosave snapshots; record errors, stale heartbeats, "
    "crash evidence, and performance warnings without running arbitrary shell commands."
)

ALLOWED_OPERATIONS = {
    "watch_gui_heartbeat",
    "read_snapshot_file",
    "write_safe_check_event",
    "write_safe_check_snapshot",
}

DIAGNOSTIC_REPORT_REQUIREMENTS = [
    "Suppress routine lifecycle noise such as normal watchdog start/close records.",
    "Record warnings/errors/critical events with enough context to reproduce or improve the behavior.",
    "Capture performance clues only when a threshold is crossed.",
    "Never capture API keys, passwords, tokens, or arbitrary command output.",
    "Never run shell commands; collect only Python/OS metadata and safe-check sidecar files.",
]

ACTIONABLE_INFO_EVENTS = {"diagnostic_report_started"}
SAFE_CHECK_SESSION_LOG_SUFFIXES = (
    ".heartbeat.json",
    ".heartbeat.json.tmp",
    ".snapshot.json",
    ".snapshot.json.tmp",
    ".diagnostic.jsonl",
    ".fatal.log",
)
DEFAULT_SAFE_CHECK_SESSION_KEEP = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_check_session_keep() -> int:
    raw_value = os.getenv("LEGAL_AGENT_SAFE_CHECK_KEEP_SESSIONS", str(DEFAULT_SAFE_CHECK_SESSION_KEEP))
    try:
        keep = int(raw_value)
    except ValueError:
        return DEFAULT_SAFE_CHECK_SESSION_KEEP
    return max(1, keep)


def safe_check_dir() -> Path:
    configured = os.getenv("LEGAL_AGENT_SAFE_CHECK_DIR")
    path = Path(configured).expanduser() if configured else Path.cwd() / ".legal_agent" / "safe_check"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_paths(session_id: str) -> tuple[Path, Path]:
    root = safe_check_dir()
    return root / f"{session_id}.heartbeat.json", root / f"{session_id}.snapshot.json"


def diagnostic_report_path(session_id: str) -> Path:
    return safe_check_dir() / f"{session_id}.diagnostic.jsonl"


def _session_id_from_log_name(name: str) -> str | None:
    for suffix in SAFE_CHECK_SESSION_LOG_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return None


def _session_group_mtime(paths: list[Path]) -> float:
    mtimes: list[float] = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def _heartbeat_for_session(session_id: str, paths: list[Path]) -> Path | None:
    heartbeat_name = f"{session_id}.heartbeat.json"
    for path in paths:
        if path.name == heartbeat_name:
            return path
    return None


def _session_is_live(session_id: str, paths: list[Path]) -> bool:
    heartbeat_path = _heartbeat_for_session(session_id, paths)
    if heartbeat_path is None:
        return False
    heartbeat = read_json(heartbeat_path)
    if str(heartbeat.get("status") or "") != "running":
        return False
    pid = heartbeat.get("pid")
    return isinstance(pid, int) and _process_is_alive(pid)


def prune_old_session_logs(root: Path | None = None, current_session_id: str | None = None) -> int:
    """Keep the newest Safe Check session file sets and remove stale older sets."""
    safe_root = root or safe_check_dir()
    keep_sessions = _safe_check_session_keep()
    try:
        files = [path for path in safe_root.iterdir() if path.is_file()]
    except OSError:
        return 0

    groups: dict[str, list[Path]] = {}
    for path in files:
        session_id = _session_id_from_log_name(path.name)
        if session_id:
            groups.setdefault(session_id, []).append(path)

    if len(groups) <= keep_sessions:
        return 0

    protected_sessions = {
        session_id
        for session_id, paths in groups.items()
        if session_id == current_session_id or _session_is_live(session_id, paths)
    }
    target_session_count = max(keep_sessions, len(protected_sessions))
    delete_count = max(0, len(groups) - target_session_count)
    if delete_count == 0:
        return 0

    candidates = [
        (_session_group_mtime(paths), session_id, paths)
        for session_id, paths in groups.items()
        if session_id not in protected_sessions
    ]
    candidates.sort(key=lambda item: (item[0], item[1]))

    deleted_sessions = 0
    for _, _, paths in candidates[:delete_count]:
        for path in paths:
            try:
                path.unlink()
            except OSError:
                pass
        deleted_sessions += 1
    return deleted_sessions


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def append_diagnostic_report(session_id: str, event_type: str, details: dict[str, Any]) -> None:
    path = diagnostic_report_path(session_id)
    entry = {
        "created_at": _utc_now(),
        "event_type": event_type,
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    if event_type == "diagnostic_report_started":
        prune_old_session_logs(path.parent, current_session_id=session_id)


def _safe_file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def collect_process_metrics(pid: int) -> dict[str, Any]:
    metrics: dict[str, Any] = {"pid": pid}
    status_path = Path("/proc") / str(pid) / "status"
    if status_path.exists():
        wanted = {"VmRSS", "VmSize", "Threads", "FDSize", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"}
        try:
            for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
                key, _, value = line.partition(":")
                if key in wanted:
                    metrics[key] = value.strip()
        except OSError:
            metrics["status_read_error"] = True
    fd_path = Path("/proc") / str(pid) / "fd"
    if fd_path.exists():
        try:
            metrics["open_fd_count"] = len(list(fd_path.iterdir()))
        except OSError:
            metrics["open_fd_count_error"] = True
    return metrics


def snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    fields = snapshot.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    field_counts = {
        str(view_name): len(view_fields)
        for view_name, view_fields in fields.items()
        if isinstance(view_fields, dict)
    }
    return {
        "current_view": snapshot.get("current_view"),
        "case_id": snapshot.get("case_id"),
        "captured_at": snapshot.get("captured_at"),
        "view_count": len(field_counts),
        "field_counts": field_counts,
    }


def build_diagnostic_context(
    session_id: str,
    pid: int,
    db_path: str | None,
    heartbeat_path: Path,
    snapshot_path: Path,
    interval_seconds: float,
    stale_seconds: float,
) -> dict[str, Any]:
    db_file = Path(db_path).expanduser() if db_path else Path.cwd() / "legal_agent.db"
    return {
        "session_id": session_id,
        "pid": pid,
        "job": SAFE_CHECK_JOB,
        "allowed_operations": sorted(ALLOWED_OPERATIONS),
        "report_requirements": DIAGNOSTIC_REPORT_REQUIREMENTS,
        "capture_policy": "database events are warning/error/critical by default; one diagnostic_report_started info record is allowed",
        "thresholds": {
            "watch_interval_seconds": interval_seconds,
            "stale_heartbeat_seconds": stale_seconds,
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
        },
        "paths": {
            "database": str(db_file),
            "database_exists": db_file.exists(),
            "database_size_bytes": _safe_file_size(db_file),
            "heartbeat": str(heartbeat_path),
            "snapshot": str(snapshot_path),
            "diagnostic_report": str(diagnostic_report_path(session_id)),
        },
        "process_metrics": collect_process_metrics(pid),
    }


def write_heartbeat(
    heartbeat_path: Path,
    session_id: str,
    pid: int,
    case_id: int | None,
    current_view: str,
    status: str = "running",
) -> None:
    atomic_write_json(
        heartbeat_path,
        {
            "session_id": session_id,
            "pid": pid,
            "case_id": case_id,
            "current_view": current_view,
            "status": status,
            "updated_at": _utc_now(),
            "allowed_operations": sorted(ALLOWED_OPERATIONS),
        },
    )


def write_snapshot_file(snapshot_path: Path, snapshot: dict[str, Any]) -> None:
    atomic_write_json(snapshot_path, snapshot)


def record_event(
    event_type: str,
    severity: str,
    source: str,
    message: str,
    details: dict[str, Any] | None = None,
    case_id: int | None = None,
    db_path: str | None = None,
) -> int:
    normalized_severity = severity.strip().lower() if isinstance(severity, str) else ""
    normalized_type = event_type.strip() if isinstance(event_type, str) else ""
    if normalized_severity == "info" and normalized_type not in ACTIONABLE_INFO_EVENTS:
        return 0
    db.init_db(db_path)
    return db.record_safe_check_event(
        event_type=event_type,
        severity=severity,
        source=source,
        message=message,
        details=details or {},
        case_id=case_id,
        db_path=db_path,
    )


def record_snapshot(
    session_id: str,
    snapshot: dict[str, Any],
    reason: str,
    case_id: int | None = None,
    view_name: str = "",
    db_path: str | None = None,
) -> int:
    db.init_db(db_path)
    return db.save_safe_check_snapshot(
        session_id=session_id,
        payload=snapshot,
        reason=reason,
        case_id=case_id,
        view_name=view_name,
        db_path=db_path,
    )


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def _file_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def watch_gui(
    session_id: str,
    pid: int,
    db_path: str | None,
    heartbeat_path: Path,
    snapshot_path: Path,
    interval_seconds: float,
    stale_seconds: float,
) -> int:
    context = build_diagnostic_context(
        session_id=session_id,
        pid=pid,
        db_path=db_path,
        heartbeat_path=heartbeat_path,
        snapshot_path=snapshot_path,
        interval_seconds=interval_seconds,
        stale_seconds=stale_seconds,
    )
    append_diagnostic_report(session_id, "diagnostic_report_started", context)
    record_event(
        "diagnostic_report_started",
        "info",
        "safe_check_watchdog",
        "Safe Check diagnostic report initialized with actionable logging thresholds.",
        context,
        db_path=db_path,
    )

    stale_reported = False
    while True:
        heartbeat = read_json(heartbeat_path)
        case_id = heartbeat.get("case_id")
        case_id = case_id if isinstance(case_id, int) else None
        status = str(heartbeat.get("status") or "")

        if status in {"closing", "closed"}:
            return 0

        heartbeat_age = _file_age_seconds(heartbeat_path)
        if heartbeat_age is None:
            if not stale_reported:
                record_event(
                    "heartbeat_missing",
                    "warning",
                    "safe_check_watchdog",
                    "GUI heartbeat file is not available yet.",
                    {
                        "session_id": session_id,
                        "heartbeat_path": str(heartbeat_path),
                        "process_metrics": collect_process_metrics(pid),
                    },
                    db_path=db_path,
                )
                append_diagnostic_report(
                    session_id,
                    "heartbeat_missing",
                    {"heartbeat_path": str(heartbeat_path), "process_metrics": collect_process_metrics(pid)},
                )
                stale_reported = True
        elif heartbeat_age > stale_seconds and not stale_reported:
            snapshot = read_json(snapshot_path)
            details = {
                "session_id": session_id,
                "heartbeat_age_seconds": round(heartbeat_age, 3),
                "stale_threshold_seconds": stale_seconds,
                "current_view": heartbeat.get("current_view"),
                "snapshot_age_seconds": _file_age_seconds(snapshot_path),
                "snapshot_summary": snapshot_summary(snapshot),
                "process_metrics": collect_process_metrics(pid),
                "improvement_hint": "Investigate the current view for blocking work on the GUI thread or slow refresh/snapshot logic.",
            }
            record_event(
                "heartbeat_stale",
                "warning",
                "safe_check_watchdog",
                "GUI heartbeat is stale; the session may be blocked or overloaded.",
                details,
                case_id=case_id,
                db_path=db_path,
            )
            append_diagnostic_report(session_id, "heartbeat_stale", details)
            stale_reported = True
        elif heartbeat_age is not None and heartbeat_age <= stale_seconds:
            stale_reported = False

        if not _process_is_alive(pid):
            snapshot = read_json(snapshot_path)
            view_name = str(snapshot.get("current_view") or heartbeat.get("current_view") or "")
            if snapshot:
                record_snapshot(
                    session_id=session_id,
                    snapshot=snapshot,
                    reason="post_crash_snapshot_file",
                    case_id=case_id,
                    view_name=view_name,
                    db_path=db_path,
                )
            details = {
                "session_id": session_id,
                "pid": pid,
                "snapshot_available": bool(snapshot),
                "snapshot_path": str(snapshot_path),
                "snapshot_age_seconds": _file_age_seconds(snapshot_path),
                "heartbeat_path": str(heartbeat_path),
                "last_heartbeat": heartbeat,
                "snapshot_summary": snapshot_summary(snapshot),
                "process_metrics": collect_process_metrics(pid),
                "improvement_hint": "Use the latest snapshot summary and last heartbeat view to narrow the crash path before reproducing.",
            }
            record_event(
                "gui_crash_or_forced_exit",
                "critical",
                "safe_check_watchdog",
                "GUI process stopped before a normal shutdown heartbeat was written.",
                details,
                case_id=case_id,
                db_path=db_path,
            )
            append_diagnostic_report(session_id, "gui_crash_or_forced_exit", details)
            return 2

        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=SAFE_CHECK_JOB)
    subparsers = parser.add_subparsers(dest="command", required=True)

    watch = subparsers.add_parser("watch", help="Watch one legal-agent-gui session.")
    watch.add_argument("--session-id", required=True)
    watch.add_argument("--pid", required=True, type=int)
    watch.add_argument("--db", default=None)
    watch.add_argument("--heartbeat", required=True)
    watch.add_argument("--snapshot", required=True)
    watch.add_argument("--interval", default=2.0, type=float)
    watch.add_argument("--stale-seconds", default=15.0, type=float)

    args = parser.parse_args(argv)
    if args.command == "watch":
        return watch_gui(
            session_id=args.session_id,
            pid=args.pid,
            db_path=args.db,
            heartbeat_path=Path(args.heartbeat),
            snapshot_path=Path(args.snapshot),
            interval_seconds=max(0.5, args.interval),
            stale_seconds=max(3.0, args.stale_seconds),
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
