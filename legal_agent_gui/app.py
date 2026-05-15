from __future__ import annotations

import os
import sys
from ctypes.util import find_library
from pathlib import Path

os.environ.setdefault("QT_LOGGING_RULES", "qt.accessibility.atspi.warning=false")

from PySide6 import QtCore, QtWidgets

from .main_window import MainWindow
from legal_agent.logger import get_logger
from legal_agent.observability import performance_checkpoint

logger = get_logger(__name__)
_previous_qt_message_handler = None
_qt_message_filter_installed = False


def _is_noisy_qt_message(message: str) -> bool:
    return (
        message.startswith("QTextCursor::setPosition: Position ") and message.endswith("out of range")
    ) or (
        "AtSpiAdaptor::applicationInterface does not implement" in message
    )


def _qt_message_handler(mode: QtCore.QtMsgType, context: QtCore.QMessageLogContext, message: str) -> None:
    if _is_noisy_qt_message(message):
        return
    if _previous_qt_message_handler:
        _previous_qt_message_handler(mode, context, message)
    else:
        print(message, file=sys.stderr)


def _install_qt_message_filter() -> None:
    global _previous_qt_message_handler, _qt_message_filter_installed
    if os.getenv("LEGAL_AGENT_VERBOSE_QT", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    if not _qt_message_filter_installed:
        _previous_qt_message_handler = QtCore.qInstallMessageHandler(_qt_message_handler)
        _qt_message_filter_installed = True


def _qt_platform() -> str:
    return os.getenv("QT_QPA_PLATFORM", "").split(";", 1)[0].strip().lower()


def _x11_socket_path(display: str) -> Path | None:
    if display.startswith("unix:"):
        display = display[5:]
    if not display.startswith(":"):
        return None
    display_number = display[1:].split(".", 1)[0]
    if not display_number.isdigit():
        return None
    return Path("/tmp/.X11-unix") / f"X{display_number}"


def _wayland_socket_path(display: str) -> Path | None:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if not runtime_dir or "/" in display:
        return None
    return Path(runtime_dir) / display


def _linux_display_preflight_error() -> str | None:
    if not sys.platform.startswith("linux"):
        return None

    platform = _qt_platform()
    if platform in {"offscreen", "minimal", "vnc", "eglfs", "linuxfb"}:
        return None

    wayland_display = os.getenv("WAYLAND_DISPLAY", "").strip()
    x11_display = os.getenv("DISPLAY", "").strip()

    if wayland_display:
        socket_path = _wayland_socket_path(wayland_display)
        if socket_path is not None and not socket_path.exists():
            return (
                f"Wayland display '{wayland_display}' is set, but {socket_path} does not exist. "
                "Start the app from your desktop session or set WAYLAND_DISPLAY to a valid display."
            )
        return None

    if x11_display:
        socket_path = _x11_socket_path(x11_display)
        if socket_path is not None and not socket_path.exists():
            return (
                f"X11 display '{x11_display}' is set, but {socket_path} does not exist. "
                "Start the app from a terminal inside your desktop session, or configure DISPLAY for a valid X server."
            )
        if platform in {"", "xcb"} and find_library("xcb-cursor") is None:
            return (
                "Qt found the X11 backend, but the system library libxcb-cursor is missing. "
                "On Debian/Ubuntu/WSL, install it with: sudo apt install libxcb-cursor0"
            )
        return None

    return (
        "No graphical display is available. Start this from a desktop terminal, "
        "or configure DISPLAY/WAYLAND_DISPLAY before launching the GUI."
    )


def run_app(db_path: str | None = None) -> None:
    """Run the GUI application with error handling."""
    preflight_error = _linux_display_preflight_error()
    if preflight_error:
        print(f"Unable to start Legal Agent GUI: {preflight_error}", file=sys.stderr)
        sys.exit(1)

    try:
        _install_qt_message_filter()
        logger.debug("Starting Legal Agent GUI Application")
        with performance_checkpoint(
            "app_startup",
            context={"db_path_supplied": bool(db_path), "qt_platform": _qt_platform() or "default"},
            slow_ms=3000,
        ):
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
            window = MainWindow(db_path=db_path)
            window.show()
            QtWidgets.QApplication.processEvents()
            logger.debug("Application window displayed")
        app.exec()
    except Exception as e:
        logger.exception("Application error")
        QtWidgets.QMessageBox.critical(None, "Application Error", 
                                       f"An unexpected error occurred:\n{str(e)}")
        sys.exit(1)
