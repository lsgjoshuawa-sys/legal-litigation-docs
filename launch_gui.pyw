#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    root_text = str(project_root)
    if sys.path[0:1] != [root_text]:
        sys.path.insert(0, root_text)

    from legal_agent.gui import run_gui

    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
