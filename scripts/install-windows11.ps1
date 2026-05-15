[CmdletBinding()]
param(
    [switch]$NoShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Test-Python312 {
    param(
        [string]$Executable,
        [string[]]$PrefixArgs = @()
    )

    & $Executable @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$PythonExe = $null
$PythonPrefixArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python312 -Executable "py" -PrefixArgs @("-3.12")) {
        $PythonExe = "py"
        $PythonPrefixArgs = @("-3.12")
    }
}

if (-not $PythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python312 -Executable "python") {
        $PythonExe = "python"
        $PythonPrefixArgs = @()
    }
}

if (-not $PythonExe) {
    throw "Python 3.12+ is required. Install it from https://www.python.org/downloads/windows/ and run this installer again."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $PythonExe @PythonPrefixArgs -m venv ".venv"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }

& $VenvPython -m pip install .
if ($LASTEXITCODE -ne 0) { throw "Failed to install the project." }

& $VenvPython -m legal_agent.cli init-db
if ($LASTEXITCODE -ne 0) { throw "Failed to initialize the database." }

if (-not $NoShortcut) {
    $Answer = Read-Host "Create a Desktop shortcut for Litigation Expert AI System? [Y/n]"
    if ([string]::IsNullOrWhiteSpace($Answer) -or $Answer -match "^(y|yes)$") {
        $Desktop = [Environment]::GetFolderPath("Desktop")
        $ShortcutPath = Join-Path $Desktop "Litigation Expert AI System.lnk"
        $Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
        if (-not (Test-Path $Pythonw)) {
            $Pythonw = $VenvPython
        }

        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $Pythonw
        $Shortcut.Arguments = "-m legal_agent.gui"
        $Shortcut.WorkingDirectory = $ProjectRoot
        $Shortcut.Description = "Open the Litigation Expert AI System GUI"
        $Shortcut.IconLocation = $Pythonw
        $Shortcut.Save()
        Write-Host "Desktop shortcut created: $ShortcutPath"
    }
}

Write-Host "Installation complete."
Write-Host "Start the GUI with: .\.venv\Scripts\python.exe -m legal_agent.gui"
