from __future__ import annotations

import atexit
import faulthandler
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from typing import Any

from PySide6 import QtCore, QtWidgets

from legal_agent import safe_check


SNAPSHOT_DEBOUNCE_MS = 1200
HEARTBEAT_MS = 5000
SLOW_SNAPSHOT_SECONDS = 0.75


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _is_sensitive_field(name: str, widget: QtWidgets.QWidget) -> bool:
    lowered = name.lower()
    if any(marker in lowered for marker in ("api_key", "password", "token", "secret")):
        return True
    if isinstance(widget, QtWidgets.QLineEdit) and widget.echoMode() == QtWidgets.QLineEdit.Password:
        return True
    return False


def _trim_value(value: Any, max_chars: int = 20000) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "\n[truncated by safe check]"
    return value


def _has_meaningful_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip()) and value != "[redacted]"
    if isinstance(value, dict):
        text = value.get("text")
        index = value.get("index")
        return isinstance(text, str) and bool(text.strip()) and isinstance(index, int) and index > 0
    return value not in {None, False}


class GuiSafeCheckSupervisor(QtCore.QObject):
    """Capture unsaved GUI input and delegate crash observation to an isolated watcher."""

    def __init__(self, main_window: QtWidgets.QMainWindow, db_path: str | None = None) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.db_path = db_path
        self.session_id = uuid.uuid4().hex
        self.heartbeat_path, self.snapshot_path = safe_check.session_paths(self.session_id)
        self.watchdog: subprocess.Popen | None = None
        self._faulthandler_file = None
        self._previous_excepthook = sys.excepthook
        self._previous_threading_excepthook = getattr(threading, "excepthook", None)
        self._previous_signal_handlers: dict[int, Any] = {}
        self._shutdown_started = False

        self.snapshot_timer = QtCore.QTimer(self)
        self.snapshot_timer.setSingleShot(True)
        self.snapshot_timer.timeout.connect(lambda: self.capture_snapshot("autosave"))

        self.heartbeat_timer = QtCore.QTimer(self)
        self.heartbeat_timer.timeout.connect(lambda: self.write_heartbeat("running"))

    def start(self) -> None:
        self._install_exception_hooks()
        self._install_signal_hooks()
        self._enable_faulthandler()
        self._connect_input_signals()
        self._start_watchdog()
        self.write_heartbeat("running")
        self.capture_snapshot("startup")
        app = QtWidgets.QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)
        self.heartbeat_timer.start(HEARTBEAT_MS)

    def _start_watchdog(self) -> None:
        command = [
            sys.executable,
            "-m",
            "legal_agent.safe_check",
            "watch",
            "--session-id",
            self.session_id,
            "--pid",
            str(os.getpid()),
            "--heartbeat",
            str(self.heartbeat_path),
            "--snapshot",
            str(self.snapshot_path),
        ]
        if self.db_path:
            command.extend(["--db", str(self.db_path)])
        try:
            self.watchdog = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            safe_check.record_event(
                "watchdog_start_failed",
                "error",
                "legal_agent_gui",
                "Safe check watchdog could not be started.",
                {"error": str(exc), "session_id": self.session_id},
                case_id=self._case_id(),
                db_path=self.db_path,
            )
            safe_check.append_diagnostic_report(
                self.session_id,
                "watchdog_start_failed",
                {"error": str(exc), "session_id": self.session_id, "improvement_hint": "Check Python path and safe_check module importability."},
            )

    def _enable_faulthandler(self) -> None:
        try:
            path = safe_check.safe_check_dir() / f"{self.session_id}.fatal.log"
            self._faulthandler_file = path.open("a", encoding="utf-8")
            faulthandler.enable(file=self._faulthandler_file, all_threads=True)
        except OSError:
            self._faulthandler_file = None

    def _install_exception_hooks(self) -> None:
        def gui_excepthook(exc_type, exc_value, exc_traceback) -> None:
            self.capture_snapshot("unhandled_exception")
            details = {
                "session_id": self.session_id,
                "current_view": self._current_view_name(),
                "snapshot_path": str(self.snapshot_path),
                "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))[-12000:],
                "improvement_hint": "Use the traceback and current_view to identify the failing UI action or refresh path.",
            }
            safe_check.record_event(
                "unhandled_exception",
                "critical",
                "legal_agent_gui",
                str(exc_value),
                details,
                case_id=self._case_id(),
                db_path=self.db_path,
            )
            safe_check.append_diagnostic_report(self.session_id, "unhandled_exception", details)
            self._previous_excepthook(exc_type, exc_value, exc_traceback)

        sys.excepthook = gui_excepthook

        if self._previous_threading_excepthook:
            def thread_excepthook(args: threading.ExceptHookArgs) -> None:
                self.capture_snapshot("thread_exception")
                details = {
                    "session_id": self.session_id,
                    "current_view": self._current_view_name(),
                    "snapshot_path": str(self.snapshot_path),
                    "thread": args.thread.name if args.thread else "",
                    "traceback": "".join(
                        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                    )[-12000:],
                    "improvement_hint": "Inspect the named worker thread and any UI refresh it may trigger.",
                }
                safe_check.record_event(
                    "thread_exception",
                    "critical",
                    "legal_agent_gui",
                    str(args.exc_value),
                    details,
                    case_id=self._case_id(),
                    db_path=self.db_path,
                )
                safe_check.append_diagnostic_report(self.session_id, "thread_exception", details)
                self._previous_threading_excepthook(args)

            threading.excepthook = thread_excepthook

    def _install_signal_hooks(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            self._previous_signal_handlers[signum] = previous

            def handler(received: int, frame, previous_handler=previous) -> None:
                if self._shutdown_started:
                    raise SystemExit(128 + received)
                self._shutdown_started = True
                self.capture_snapshot(f"signal_{received}")
                self.write_heartbeat("closing")
                details = {
                    "session_id": self.session_id,
                    "signal": received,
                    "current_view": self._current_view_name(),
                    "snapshot_path": str(self.snapshot_path),
                    "improvement_hint": "If this was not intentional, inspect terminal/session manager shutdown timing.",
                }
                safe_check.record_event(
                    "gui_signal_shutdown",
                    "warning",
                    "legal_agent_gui",
                    f"GUI received signal {received}; latest editable fields were snapshotted.",
                    details,
                    case_id=self._case_id(),
                    db_path=self.db_path,
                )
                safe_check.append_diagnostic_report(self.session_id, "gui_signal_shutdown", details)
                if callable(previous_handler) and previous_handler is not signal.default_int_handler:
                    try:
                        previous_handler(received, frame)
                    except (KeyboardInterrupt, SystemExit):
                        pass
                raise SystemExit(128 + received)

            signal.signal(signum, handler)

    def _connect_input_signals(self) -> None:
        for widget in self.main_window.findChildren(QtWidgets.QLineEdit):
            widget.textEdited.connect(lambda *_: self.schedule_snapshot())
        for widget in self.main_window.findChildren(QtWidgets.QTextEdit):
            if not widget.isReadOnly():
                widget.textChanged.connect(lambda *_: self.schedule_snapshot())
        for widget in self.main_window.findChildren(QtWidgets.QPlainTextEdit):
            if not widget.isReadOnly():
                widget.textChanged.connect(lambda *_: self.schedule_snapshot())
        for widget in self.main_window.findChildren(QtWidgets.QComboBox):
            widget.currentTextChanged.connect(lambda *_: self.schedule_snapshot())
        for widget in self.main_window.findChildren(QtWidgets.QCheckBox):
            widget.toggled.connect(lambda *_: self.schedule_snapshot())
        for widget in self.main_window.findChildren(QtWidgets.QSpinBox):
            widget.valueChanged.connect(lambda *_: self.schedule_snapshot())
        for widget in self.main_window.findChildren(QtWidgets.QDoubleSpinBox):
            widget.valueChanged.connect(lambda *_: self.schedule_snapshot())

    def schedule_snapshot(self) -> None:
        if self._shutdown_started:
            return
        self.snapshot_timer.start(SNAPSHOT_DEBOUNCE_MS)

    def write_heartbeat(self, status: str) -> None:
        safe_check.write_heartbeat(
            self.heartbeat_path,
            session_id=self.session_id,
            pid=os.getpid(),
            case_id=self._case_id(),
            current_view=self._current_view_name(),
            status=status,
        )

    def capture_snapshot(self, reason: str) -> None:
        start = time.monotonic()
        snapshot = self.collect_snapshot(reason)
        safe_check.write_snapshot_file(self.snapshot_path, snapshot)
        if self._snapshot_has_meaningful_content(snapshot):
            safe_check.record_snapshot(
                session_id=self.session_id,
                snapshot=snapshot,
                reason=reason,
                case_id=self._case_id(),
                view_name=self._current_view_name(),
                db_path=self.db_path,
            )
        elapsed = time.monotonic() - start
        if elapsed > SLOW_SNAPSHOT_SECONDS:
            details = {
                "session_id": self.session_id,
                "elapsed_seconds": round(elapsed, 3),
                "threshold_seconds": SLOW_SNAPSHOT_SECONDS,
                "reason": reason,
                "current_view": self._current_view_name(),
                "field_summary": self._field_summary(snapshot),
                "improvement_hint": "Reduce expensive widget traversal or defer snapshot work for the current view.",
            }
            safe_check.record_event(
                "slow_snapshot",
                "warning",
                "legal_agent_gui",
                "Safe check snapshot took longer than expected.",
                details,
                case_id=self._case_id(),
                db_path=self.db_path,
            )
            safe_check.append_diagnostic_report(self.session_id, "slow_snapshot", details)
        self.write_heartbeat("running")

    def collect_snapshot(self, reason: str) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "captured_at": _utc_now(),
            "reason": reason,
            "case_id": self._case_id(),
            "current_view": self._current_view_name(),
            "job": safe_check.SAFE_CHECK_JOB,
            "allowed_operations": sorted(safe_check.ALLOWED_OPERATIONS),
            "fields": self._collect_editable_fields(),
        }

    def _collect_editable_fields(self) -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        views = getattr(self.main_window, "views", {})
        for view_name, view in views.items():
            if view_name == "Settings":
                continue
            view_fields: dict[str, Any] = {}
            for attribute_name, value in vars(view).items():
                if isinstance(value, QtWidgets.QWidget):
                    captured = self._widget_value(attribute_name, value)
                    if captured is not None:
                        view_fields[attribute_name] = captured
            if view_fields:
                fields[view_name] = view_fields
        return fields

    def _widget_value(self, name: str, widget: QtWidgets.QWidget) -> Any:
        if _is_sensitive_field(name, widget):
            return "[redacted]"
        if isinstance(widget, QtWidgets.QLineEdit):
            return _trim_value(widget.text())
        if isinstance(widget, QtWidgets.QTextEdit) and not widget.isReadOnly():
            return _trim_value(widget.toPlainText())
        if isinstance(widget, QtWidgets.QPlainTextEdit) and not widget.isReadOnly():
            return _trim_value(widget.toPlainText())
        if isinstance(widget, QtWidgets.QComboBox):
            return {"text": widget.currentText(), "index": widget.currentIndex()}
        if isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return widget.value()
        return None

    def _snapshot_has_meaningful_content(self, snapshot: dict[str, Any]) -> bool:
        fields = snapshot.get("fields")
        if not isinstance(fields, dict):
            return False
        for view_fields in fields.values():
            if isinstance(view_fields, dict) and any(_has_meaningful_value(value) for value in view_fields.values()):
                return True
        return False

    def _field_summary(self, snapshot: dict[str, Any]) -> dict[str, int]:
        fields = snapshot.get("fields")
        if not isinstance(fields, dict):
            return {}
        return {
            str(view_name): len(view_fields)
            for view_name, view_fields in fields.items()
            if isinstance(view_fields, dict)
        }

    def _case_id(self) -> int | None:
        case_id = getattr(self.main_window, "current_case_id", None)
        return case_id if isinstance(case_id, int) else None

    def _current_view_name(self) -> str:
        sidebar = getattr(self.main_window, "sidebar", None)
        if isinstance(sidebar, QtWidgets.QListWidget) and sidebar.currentItem():
            return sidebar.currentItem().text()
        return ""

    def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self.snapshot_timer.stop()
        self.capture_snapshot("normal_shutdown")
        self.write_heartbeat("closing")
        sys.excepthook = self._previous_excepthook
        if self._previous_threading_excepthook:
            threading.excepthook = self._previous_threading_excepthook
        for signum, previous in self._previous_signal_handlers.items():
            signal.signal(signum, previous)
        if self._faulthandler_file:
            try:
                faulthandler.disable()
                self._faulthandler_file.close()
            except OSError:
                pass


def install_safe_check(main_window: QtWidgets.QMainWindow, db_path: str | None = None) -> GuiSafeCheckSupervisor:
    supervisor = GuiSafeCheckSupervisor(main_window, db_path)
    supervisor.start()
    atexit.register(supervisor.shutdown)
    return supervisor
