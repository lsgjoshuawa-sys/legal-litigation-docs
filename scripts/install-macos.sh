#!/usr/bin/env sh
set -eu

script_path=$0
if command -v perl >/dev/null 2>&1; then
    script_path=$(perl -MCwd=abs_path -e 'print abs_path(shift)' "$0")
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$script_path")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$project_root"

find_python() {
    for candidate in "${PYTHON_BIN:-}" python3.12 python3; do
        [ -n "$candidate" ] || continue
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
                printf '%s\n' "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

python_bin=$(find_python) || {
    printf '%s\n' "Python 3.12+ is required. Install it, then run this installer again." >&2
    exit 1
}

if [ ! -x "$project_root/.venv/bin/python" ]; then
    "$python_bin" -m venv "$project_root/.venv"
fi

"$project_root/.venv/bin/python" -m pip install --upgrade pip
"$project_root/.venv/bin/python" -m pip install .
"$project_root/.venv/bin/python" -m legal_agent.cli init-db

create_shortcut=yes
printf '%s' "Create a Desktop shortcut for Litigation Expert AI System? [Y/n] "
read answer || answer=
case "$answer" in
    n|N|no|NO|No) create_shortcut=no ;;
esac

if [ "$create_shortcut" = yes ]; then
    desktop_dir="$HOME/Desktop"
    app_dir="$desktop_dir/Litigation Expert AI System.app"
    contents_dir="$app_dir/Contents"
    macos_dir="$contents_dir/MacOS"
    mkdir -p "$macos_dir"

    cat > "$contents_dir/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIdentifier</key>
    <string>local.legalagent.gui</string>
    <key>CFBundleName</key>
    <string>Litigation Expert AI System</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
</dict>
</plist>
EOF

    cat > "$macos_dir/launch" <<EOF
#!/bin/sh
cd "$project_root"
exec "$project_root/.venv/bin/python" -m legal_agent.gui
EOF
    chmod +x "$macos_dir/launch"
    printf '%s\n' "Desktop shortcut created: $app_dir"
fi

printf '%s\n' "Installation complete."
printf '%s\n' "Start the GUI with: $project_root/legal-agent-gui"

