# Clean Installation

## One-Click Graphical Installer

Double-click `START_INSTALLER.pyw` in the project root to open the guided installer. It walks through features, examples, required API key setup, local installation, database initialization, and the option to create a Desktop shortcut.

The graphical installer requires Python with Tkinter support. Python.org Windows and macOS installers normally include Tkinter. On some Linux distributions, install the `python3-tk` system package if the installer window does not open.

The OpenAI API key is required before the installer will start the application. CourtListener is optional and can be enabled during installation.

## Command-Line Installers

Use the installer for your operating system from the project root. Each installer creates a local `.venv`, installs the app, initializes `legal_agent.db`, and asks whether to create a desktop shortcut for the GUI.

## Windows 11

1. Install Python 3.12 or newer from <https://www.python.org/downloads/windows/>.
2. Open PowerShell in the project folder.
3. Run:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\install-windows11.ps1
```

When prompted, choose `Y` to create a Desktop shortcut named `Litigation Expert AI System`.

## Linux

1. Install Python 3.12 or newer.
2. If your distro needs Qt's XCB cursor package, install it first. On Ubuntu/Debian:

```bash
sudo apt install python3.12 python3.12-venv libxcb-cursor0
```

3. Run:

```bash
./scripts/install-linux.sh
```

When prompted, choose `Y` to create a Desktop launcher.

## macOS

1. Install Python 3.12 or newer from <https://www.python.org/downloads/macos/> or Homebrew.
2. Run:

```bash
./scripts/install-macos.sh
```

When prompted, choose `Y` to create a Desktop app shortcut.

## Start The App

After installation, use the Desktop shortcut or run one of these commands from the project root:

```bash
./legal-agent-gui
```

```bash
.venv/bin/python -m legal_agent.gui
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m legal_agent.gui
```

## Configuration

Copy `.env.example` to `.env` or enter your OpenAI API key in the Settings page. Keep `.env`, local databases, logs, and exported client data out of source control.
