#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import sys
from pathlib import Path


def _show_startup_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Installer Startup Error", message)
        root.destroy()
        return
    except Exception:
        pass

    if sys.platform.startswith("win"):
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "Installer Startup Error", 0x10)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def main() -> int:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    try:
        from scripts.gui_installer import main as installer_main
    except Exception as exc:
        _show_startup_error(
            "The graphical installer could not start.\n\n"
            "Make sure Python includes Tkinter. On Linux this may require the python3-tk package.\n\n"
            f"Details: {exc}"
        )
        return 1
    return installer_main()


if __name__ == "__main__":
    raise SystemExit(main())

