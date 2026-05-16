from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Callable

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


APP_NAME = "Litigation Expert AI System"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_COURTLISTENER_BASE_URL = "https://www.courtlistener.com/api/rest/v4"
PLACEHOLDER_OPENAI_KEY = "your_openai_api_key_here"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    missing = [key for key in updates if key not in seen]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={updates[key]}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def valid_openai_key(api_key: str) -> bool:
    cleaned = api_key.strip()
    return bool(cleaned) and cleaned != PLACEHOLDER_OPENAI_KEY and not any(char.isspace() for char in cleaned)


def python_version_ok(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command + ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def find_python_command() -> list[str]:
    candidates: list[list[str]] = []
    if sys.version_info >= (3, 12):
        candidates.append([sys.executable])
    if platform.system() == "Windows":
        candidates.extend([["py", "-3.12"], ["python"]])
    else:
        candidates.extend([["python3.12"], ["python3"], ["python"]])

    for command in candidates:
        if python_version_ok(command):
            return command
    raise RuntimeError("Python 3.12 or newer is required.")


def venv_python(root: Path, prefer_windowed: bool = False) -> Path:
    if platform.system() == "Windows":
        executable = "pythonw.exe" if prefer_windowed else "python.exe"
        path = root / ".venv" / "Scripts" / executable
        if prefer_windowed and not path.exists():
            return root / ".venv" / "Scripts" / "python.exe"
        return path
    return root / ".venv" / "bin" / "python"


def run_command(command: list[str], cwd: Path, log: Callable[[str], None]) -> None:
    log("$ " + " ".join(str(part) for part in command))
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        log(line.rstrip())
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"Command failed with exit code {return_code}.")


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_windows_shortcut(root: Path, log: Callable[[str], None]) -> None:
    pythonw = venv_python(root, prefer_windowed=True)
    launcher = root / "launch_gui.pyw"
    launcher_argument = f'"{launcher}"'
    script_dir = root / ".legal_agent"
    script_dir.mkdir(parents=True, exist_ok=True)
    shortcut_script = script_dir / "create_desktop_shortcut.ps1"
    shortcut_script.write_text(
        "\n".join(
            [
                '$Desktop = [Environment]::GetFolderPath("Desktop")',
                f"$ShortcutPath = Join-Path $Desktop {_powershell_literal(APP_NAME + '.lnk')}",
                "$Shell = New-Object -ComObject WScript.Shell",
                "$Shortcut = $Shell.CreateShortcut($ShortcutPath)",
                f"$Shortcut.TargetPath = {_powershell_literal(str(pythonw))}",
                f"$Shortcut.Arguments = {_powershell_literal(launcher_argument)}",
                f"$Shortcut.WorkingDirectory = {_powershell_literal(str(root))}",
                f"$Shortcut.Description = {_powershell_literal('Open the ' + APP_NAME + ' GUI')}",
                f"$Shortcut.IconLocation = {_powershell_literal(str(pythonw))}",
                "$Shortcut.Save()",
                'Write-Host "Desktop shortcut created: $ShortcutPath"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_command(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(shortcut_script)],
        cwd=root,
        log=log,
    )


def create_macos_shortcut(root: Path, log: Callable[[str], None]) -> None:
    desktop_dir = Path.home() / "Desktop"
    app_dir = desktop_dir / f"{APP_NAME}.app"
    contents_dir = app_dir / "Contents"
    macos_dir = contents_dir / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)
    (contents_dir / "Info.plist").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIdentifier</key>
    <string>local.legalagent.gui</string>
    <key>CFBundleName</key>
    <string>{APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    launcher = macos_dir / "launch"
    launcher.write_text(
        f"""#!/bin/sh
cd "{root}"
exec "{venv_python(root)}" "{root / "launch_gui.pyw"}"
""",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    log(f"Desktop app shortcut created: {app_dir}")


def create_linux_shortcut(root: Path, log: Callable[[str], None]) -> None:
    desktop_dir = Path(os.getenv("XDG_DESKTOP_DIR", str(Path.home() / "Desktop")))
    applications_dir = Path.home() / ".local" / "share" / "applications"
    applications_dir.mkdir(parents=True, exist_ok=True)
    launcher_file = applications_dir / "legal-agent-gui.desktop"
    launcher_text = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Open the {APP_NAME} GUI
Exec="{root / "legal-agent-gui"}"
Path={root}
Terminal=false
Categories=Office;Utility;
"""
    launcher_file.write_text(launcher_text, encoding="utf-8")
    launcher_file.chmod(0o755)

    if desktop_dir.exists():
        desktop_file = desktop_dir / f"{APP_NAME}.desktop"
        desktop_file.write_text(launcher_text, encoding="utf-8")
        desktop_file.chmod(0o755)
        log(f"Desktop shortcut created: {desktop_file}")
    else:
        log(f"Application launcher created: {launcher_file}")
        log(f"Desktop folder was not found at {desktop_dir}.")


def create_desktop_shortcut(root: Path, log: Callable[[str], None]) -> None:
    system = platform.system()
    if system == "Windows":
        create_windows_shortcut(root, log)
    elif system == "Darwin":
        create_macos_shortcut(root, log)
    else:
        create_linux_shortcut(root, log)


def launch_app(root: Path) -> None:
    executable = venv_python(root, prefer_windowed=platform.system() == "Windows")
    subprocess.Popen([str(executable), str(root / "launch_gui.pyw")], cwd=str(root))


class InstallerWizard:
    def __init__(self, root_window: tk.Tk, root: Path) -> None:
        self.window = root_window
        self.root = root
        self.env_path = root / ".env"
        existing_env = parse_env_file(self.env_path)

        self.step = 0
        self.install_started = False
        self.install_finished = False
        self.messages: Queue[tuple[str, str]] = Queue()

        self.openai_key = tk.StringVar(value=existing_env.get("OPENAI_API_KEY", ""))
        self.model = tk.StringVar(value=existing_env.get("LEGAL_AGENT_OPENAI_MODEL", DEFAULT_MODEL))
        self.courtlistener_enabled = tk.BooleanVar(
            value=existing_env.get("COURTLISTENER_ENABLED", "false").lower() == "true"
        )
        self.courtlistener_token = tk.StringVar(value=existing_env.get("COURTLISTENER_API_TOKEN", ""))
        self.courtlistener_base_url = tk.StringVar(
            value=existing_env.get("COURTLISTENER_BASE_URL", DEFAULT_COURTLISTENER_BASE_URL)
        )
        self.create_shortcut = tk.BooleanVar(value=True)
        self.launch_when_done = tk.BooleanVar(value=True)
        self.show_key = tk.BooleanVar(value=False)

        self.window.title(f"{APP_NAME} Installer")
        self.window.geometry("780x560")
        self.window.minsize(700, 500)

        self.container = ttk.Frame(self.window, padding=18)
        self.container.pack(fill="both", expand=True)
        self.content = ttk.Frame(self.container)
        self.content.pack(fill="both", expand=True)
        self.button_bar = ttk.Frame(self.container)
        self.button_bar.pack(fill="x", pady=(14, 0))

        self.back_button = ttk.Button(self.button_bar, text="Back", command=self.back)
        self.back_button.pack(side="left")
        self.next_button = ttk.Button(self.button_bar, text="Next", command=self.next)
        self.next_button.pack(side="right")
        self.cancel_button = ttk.Button(self.button_bar, text="Cancel", command=self.window.destroy)
        self.cancel_button.pack(side="right", padx=(0, 8))

        self.progress: ttk.Progressbar | None = None
        self.log_box: scrolledtext.ScrolledText | None = None
        self.render()
        self.window.after(150, self.consume_messages)

    def clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def heading(self, title: str, subtitle: str = "") -> None:
        ttk.Label(self.content, text=title, font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        if subtitle:
            ttk.Label(self.content, text=subtitle, wraplength=700).pack(anchor="w", pady=(6, 16))

    def render(self) -> None:
        self.clear_content()
        if self.step == 0:
            self.render_welcome()
        elif self.step == 1:
            self.render_api_keys()
        elif self.step == 2:
            self.render_options()
        else:
            self.render_install()
        self.sync_buttons()

    def render_welcome(self) -> None:
        self.heading(
            "Install Litigation Expert AI System",
            "This wizard installs the app locally, prepares the database, and can create a Desktop shortcut.",
        )
        features = [
            "Case intake, parties, facts, claims, evidence, action items, and deadlines.",
            "Authority validation, citation treatment tracking, and verified-authority drafting controls.",
            "CourtListener research tools for public legal research and citation checks.",
            "AI argument analysis with throttling and strict citation guardrails.",
            "Safe Check watchdog snapshots unsaved work and trims old session logs automatically.",
        ]
        examples = [
            'Example: create a case titled "Example Matter" and classify the procedure track.',
            "Example: store a verified authority, then use it in a draft outline.",
            "Example: export a case profile to Markdown for review.",
        ]
        ttk.Label(self.content, text="Features", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(4, 4))
        for item in features:
            ttk.Label(self.content, text=f"- {item}", wraplength=700).pack(anchor="w", padx=(14, 0))
        ttk.Label(self.content, text="Examples", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(18, 4))
        for item in examples:
            ttk.Label(self.content, text=f"- {item}", wraplength=700).pack(anchor="w", padx=(14, 0))
        ttk.Label(
            self.content,
            text="Before startup, the installer requires an OpenAI API key so AI features are configured from the beginning.",
            wraplength=700,
        ).pack(anchor="w", pady=(18, 0))

    def render_api_keys(self) -> None:
        self.heading("API Keys", "Enter the credentials the app needs before first startup.")
        form = ttk.Frame(self.content)
        form.pack(fill="x", anchor="w")

        ttk.Label(form, text="OpenAI API key").grid(row=0, column=0, sticky="w", pady=6)
        self.api_entry = ttk.Entry(form, textvariable=self.openai_key, show="" if self.show_key.get() else "*", width=58)
        self.api_entry.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=6)
        ttk.Checkbutton(form, text="Show", variable=self.show_key, command=self.render).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(form, text="OpenAI model").grid(row=1, column=0, sticky="w", pady=6)
        model_box = ttk.Combobox(form, textvariable=self.model, values=["gpt-4o-mini", "gpt-4o", "gpt-4o-large"], width=24)
        model_box.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=6)

        ttk.Separator(self.content).pack(fill="x", pady=14)
        ttk.Checkbutton(
            self.content,
            text="Enable CourtListener research during installation",
            variable=self.courtlistener_enabled,
        ).pack(anchor="w")

        court_form = ttk.Frame(self.content)
        court_form.pack(fill="x", anchor="w", pady=(8, 0))
        ttk.Label(court_form, text="CourtListener API token").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(court_form, textvariable=self.courtlistener_token, width=58, show="*").grid(
            row=0, column=1, sticky="ew", padx=(12, 0), pady=6
        )
        ttk.Label(court_form, text="CourtListener base URL").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(court_form, textvariable=self.courtlistener_base_url, width=58).grid(
            row=1, column=1, sticky="ew", padx=(12, 0), pady=6
        )
        form.columnconfigure(1, weight=1)
        court_form.columnconfigure(1, weight=1)

    def render_options(self) -> None:
        self.heading("Install Options", "Review the local install choices before setup begins.")
        rows = [
            ("Project folder", str(self.root)),
            ("Virtual environment", str(self.root / ".venv")),
            ("Database", str(self.root / "legal_agent.db")),
            ("Environment file", str(self.env_path)),
        ]
        for label, value in rows:
            row = ttk.Frame(self.content)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=f"{label}:", width=20).pack(side="left")
            ttk.Label(row, text=value, wraplength=560).pack(side="left", fill="x", expand=True)

        ttk.Separator(self.content).pack(fill="x", pady=16)
        ttk.Checkbutton(
            self.content,
            text="Create Desktop shortcut when installation is finished",
            variable=self.create_shortcut,
        ).pack(anchor="w", pady=4)
        ttk.Checkbutton(
            self.content,
            text="Start the GUI after installation completes",
            variable=self.launch_when_done,
        ).pack(anchor="w", pady=4)
        ttk.Label(
            self.content,
            text="Next will start installation. The installer may download Python packages if they are not already cached.",
            wraplength=700,
        ).pack(anchor="w", pady=(18, 0))

    def render_install(self) -> None:
        self.heading("Installing", "Follow the progress messages until setup completes.")
        self.progress = ttk.Progressbar(self.content, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 12))
        self.log_box = scrolledtext.ScrolledText(self.content, height=18, wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")
        if not self.install_started:
            self.install_started = True
            self.progress.start(10)
            threading.Thread(target=self.install, daemon=True).start()

    def sync_buttons(self) -> None:
        self.back_button.configure(state="disabled" if self.step == 0 or self.install_started else "normal")
        if self.step < 2:
            self.next_button.configure(text="Next", state="normal")
        elif self.step == 2:
            self.next_button.configure(text="Install", state="normal")
        else:
            self.next_button.configure(text="Finish", state="normal" if self.install_finished else "disabled")
        self.cancel_button.configure(text="Close" if self.install_finished else "Cancel")

    def back(self) -> None:
        if self.step > 0 and not self.install_started:
            self.step -= 1
            self.render()

    def next(self) -> None:
        if self.step == 1 and not self.validate_api_keys():
            return
        if self.step < 3:
            self.step += 1
            self.render()
        else:
            self.window.destroy()

    def validate_api_keys(self) -> bool:
        if not valid_openai_key(self.openai_key.get()):
            messagebox.showerror(
                "OpenAI API Key Required",
                "Enter a valid OpenAI API key before installation. The app will not be started without it.",
            )
            return False
        if self.courtlistener_enabled.get() and not self.courtlistener_token.get().strip():
            messagebox.showerror(
                "CourtListener Token Required",
                "CourtListener is enabled, so enter a CourtListener API token or turn CourtListener off.",
            )
            return False
        return True

    def log(self, message: str) -> None:
        self.messages.put(("log", message))

    def install_done(self, message: str) -> None:
        self.messages.put(("done", message))

    def install_failed(self, message: str) -> None:
        self.messages.put(("error", message))

    def install(self) -> None:
        try:
            self.log("Preparing API key configuration.")
            updates = {
                "OPENAI_API_KEY": self.openai_key.get().strip(),
                "LEGAL_AGENT_OPENAI_MODEL": self.model.get().strip() or DEFAULT_MODEL,
                "LEGAL_AGENT_OPENAI_MAX_REQUESTS_PER_MINUTE": "20",
                "COURTLISTENER_ENABLED": "true" if self.courtlistener_enabled.get() else "false",
                "COURTLISTENER_API_TOKEN": self.courtlistener_token.get().strip(),
                "COURTLISTENER_BASE_URL": self.courtlistener_base_url.get().strip() or DEFAULT_COURTLISTENER_BASE_URL,
                "LEGAL_AGENT_SAFE_CHECK_KEEP_SESSIONS": "3",
            }
            update_env_file(self.env_path, updates)
            self.log("Saved .env configuration. API secrets are stored locally only.")

            python_command = find_python_command()
            self.log("Using Python installer runtime: " + " ".join(python_command))
            if not venv_python(self.root).exists():
                run_command(python_command + ["-m", "venv", str(self.root / ".venv")], self.root, self.log)
            else:
                self.log("Existing .venv found. Reusing it.")

            python = str(venv_python(self.root))
            run_command([python, "-m", "pip", "install", "--upgrade", "pip"], self.root, self.log)
            run_command([python, "-m", "pip", "install", "."], self.root, self.log)
            run_command([python, "-m", "legal_agent.cli", "init-db"], self.root, self.log)

            if self.create_shortcut.get():
                self.log("Creating Desktop shortcut.")
                create_desktop_shortcut(self.root, self.log)

            if self.launch_when_done.get():
                self.log("Starting the GUI.")
                launch_app(self.root)

            self.install_done("Installation complete.")
        except Exception as exc:
            self.install_failed(str(exc))

    def consume_messages(self) -> None:
        try:
            while True:
                kind, message = self.messages.get_nowait()
                if kind == "log":
                    self.append_log(message)
                elif kind == "done":
                    self.append_log(message)
                    self.install_finished = True
                    if self.progress:
                        self.progress.stop()
                    messagebox.showinfo("Installation Complete", message)
                    self.sync_buttons()
                elif kind == "error":
                    self.append_log("ERROR: " + message)
                    self.install_finished = True
                    if self.progress:
                        self.progress.stop()
                    messagebox.showerror("Installation Failed", message)
                    self.sync_buttons()
        except Empty:
            pass
        self.window.after(150, self.consume_messages)

    def append_log(self, message: str) -> None:
        if self.log_box is None:
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def main() -> int:
    root_window = tk.Tk()
    InstallerWizard(root_window, project_root())
    root_window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
