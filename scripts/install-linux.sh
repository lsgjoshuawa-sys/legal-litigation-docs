#!/usr/bin/env sh
set -eu

script_path=$0
if command -v readlink >/dev/null 2>&1; then
    script_path=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
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
    desktop_dir="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
    applications_dir="$HOME/.local/share/applications"
    launcher_file="$applications_dir/legal-agent-gui.desktop"
    mkdir -p "$applications_dir"

    cat > "$launcher_file" <<EOF
[Desktop Entry]
Type=Application
Name=Litigation Expert AI System
Comment=Open the Litigation Expert AI System GUI
Exec="$project_root/legal-agent-gui"
Path=$project_root
Terminal=false
Categories=Office;Utility;
EOF
    chmod +x "$launcher_file"

    if [ -d "$desktop_dir" ]; then
        desktop_file="$desktop_dir/Litigation Expert AI System.desktop"
        cp "$launcher_file" "$desktop_file"
        chmod +x "$desktop_file"
        printf '%s\n' "Desktop shortcut created: $desktop_file"
    else
        printf '%s\n' "App launcher created: $launcher_file"
        printf '%s\n' "Desktop folder was not found at $desktop_dir."
    fi
fi

printf '%s\n' "Installation complete."
printf '%s\n' "Start the GUI with: $project_root/legal-agent-gui"

