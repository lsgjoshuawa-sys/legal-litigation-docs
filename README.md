# Litigation Expert AI System

A command-line legal operations and litigation drafting assistant built in Python.

## Features

- Case intake tracking for facts, parties, claims, evidence, and actions
- Jurisdiction classification for California Superior Court, Eastern District of California, and local government disputes
- Procedural rule identification by track
- Manual authority research logging and verification
- Treatment status tracking for authorities
- Claim element checklists and evidence sufficiency review
- Document outline and draft generation with verified authorities only
- Vulnerability analysis for pleading and filing readiness
- Export to Markdown, JSON, and TXT
- SQLite local storage

## Installation

For a clean OS-specific setup, use the root install guide:

```bash
cat INSTALL.md
```

Quick installers are available:

- Windows 11: `PowerShell -ExecutionPolicy Bypass -File .\scripts\install-windows11.ps1`
- Linux: `./scripts/install-linux.sh`
- macOS: `./scripts/install-macos.sh`

Each installer creates `.venv`, installs the app, initializes the database, and asks whether to create a Desktop shortcut for the GUI.

### Manual Install

1. Install Python 3.12+.
2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate       # Windows
```

3. Install dependencies from `requirements.txt` or install the package directly:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Or install the package for command-line entry points:

```bash
python -m pip install .
```

4. Use the repository folder as your working directory.
5. Initialize the database:

```bash
python -m legal_agent.cli init-db
```

If the package is installed, you can also run:

```bash
legal-agent init-db
```

## GUI startup

From the project folder, the GUI can be started with:

```bash
./legal-agent-gui
```

If the package entry points are installed and your virtual environment is active, this is equivalent to:

```bash
legal-agent-gui
python -m legal_agent.gui
```

On Linux or WSL, start the GUI from a terminal connected to a desktop session. If Qt reports that the `xcb` platform plugin cannot initialize because `libxcb-cursor` is missing, install the system package:

```bash
sudo apt install libxcb-cursor0
```

### Safe Check session protection

The GUI starts an isolated Safe Check watchdog for each session. Its job is limited to observing the GUI heartbeat, reading the latest autosaved snapshot file, and writing safe-check events/snapshots to SQLite. It does not run arbitrary shell commands.

While you type, editable GUI fields are silently snapshotted into the local database and `.legal_agent/safe_check/`. Password/API-key fields are redacted. The Save buttons still matter: they commit the current draft into the appropriate case list or table, while Safe Check preserves unsaved progress if the GUI crashes before you click Save.

Safe Check records are visible in the Audit Log / Verification History panel.

Safe Check logging is intentionally issue-focused. It suppresses routine start/close noise and records details when a threshold or failure condition is useful for improvement work:

- stale heartbeat, including current view, heartbeat age, snapshot age, and process metrics
- crash or forced exit, including last heartbeat, latest snapshot summary, and file paths
- slow snapshot, including elapsed time, threshold, current view, and field counts
- unhandled exception or thread exception, including traceback and current view
- watchdog startup failure

Each session also creates a diagnostic report in `.legal_agent/safe_check/*.diagnostic.jsonl` with the capture policy, allowed operations, runtime context, thresholds, and actionable follow-up details. Routine application lifecycle messages are DEBUG-only by default. Set `LEGAL_AGENT_LOG_LEVEL=DEBUG` when you intentionally want verbose investigation logs.

Safe Check automatically keeps the newest three session file sets in `.legal_agent/safe_check/` and removes older inactive session logs as new watchdog sessions start. Running GUI sessions are protected by heartbeat/PID checks. Set `LEGAL_AGENT_SAFE_CHECK_KEEP_SESSIONS` if you need a different retention count.

## Windows 11 specific install

1. Open PowerShell and navigate to the project folder.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install the project and dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install .
```

4. Initialize the database:

```powershell
legal-agent init-db
```

5. Run the CLI or GUI:

```powershell
legal-agent new-case --title "Example Case" --legal-track A
legal-agent-gui
```

If you prefer module mode rather than installed scripts:

```powershell
python -m legal_agent.cli new-case --title "Example Case" --legal-track A
python -m legal_agent.gui
```

## Usage

Basic commands:

```bash
python -m legal_agent.cli new-case --title "Example Case" --legal-track A
python -m legal_agent.cli add-party --case-id 1 --name "Plaintiff" --role plaintiff
python -m legal_agent.cli add-claim --case-id 1 --claim-name "Negligence" --required-elements '["Duty", "Breach", "Causation", "Damages"]'
python -m legal_agent.cli add-evidence --case-id 1 --title "Report" --supports-claims '["Negligence"]'
python -m legal_agent.cli classify --case-id 1
python -m legal_agent.cli outline-document --case-id 1 --type complaint
python -m legal_agent.cli draft-document --case-id 1 --type complaint
python -m legal_agent.cli export --case-id 1 --format markdown
```

## Running tests

```bash
HOME=/tmp/legal-agent-home python -m unittest discover tests
```

The temporary `HOME` keeps local test logs and settings out of the user profile. Any writable directory can be used.

## Production Readiness

- Copy `.env.example` to `.env` or configure the same variables in a managed secret store.
- Keep `.env`, `.Tenv`, SQLite databases, and logs out of source control.
- Review `docs/DEPLOYMENT.md` for release steps and the security checklist.
- Review `docs/DISASTER_RECOVERY.md` for backup, restore, and incident procedures.

## CourtListener REST API

CourtListener support is disabled by default and only sends data when a user explicitly runs a query from the CourtListener Research panel or connector API.

```bash
COURTLISTENER_ENABLED=true
COURTLISTENER_API_TOKEN=your_courtlistener_token
COURTLISTENER_BASE_URL=https://www.courtlistener.com/api/rest/v4
```

Example connector usage:

```python
from legal_agent.connectors.courtlistener_connector import CourtListenerConnector

connector = CourtListenerConnector()
results = connector.search_legal("specific performance contract damages", court="ca9")
citations = connector.lookup_citation(text="Obergefell v. Hodges, 576 U.S. 644")
```

Use `lookup_citation(...)` as a citation-verification guardrail for AI-generated legal drafts before relying on citations in filing work.

## Resource Throttling

Application-level throttling is enabled by default for AI calls, CourtListener HTTP calls, AI context size, output tokens, and citation-validation breadth. Configure the shared throttling agent with `.env` values:

```bash
LEGAL_AGENT_THROTTLE_ENABLED=true
LEGAL_AGENT_AI_MAX_REQUESTS_PER_MINUTE=6
LEGAL_AGENT_AI_MAX_CONCURRENT_REQUESTS=1
LEGAL_AGENT_AI_MAX_CONTEXT_CHARS=12000
LEGAL_AGENT_AI_MAX_OUTPUT_TOKENS=800
LEGAL_AGENT_HTTP_MAX_REQUESTS_PER_MINUTE=30
LEGAL_AGENT_HTTP_MAX_CONCURRENT_REQUESTS=2
LEGAL_AGENT_CITATION_CHECKS_PER_RUN=8
LEGAL_AGENT_THROTTLE_MAX_WAIT_SECONDS=30
```

The AI layer receives these limits in its mandatory prompt procedure, and the API wrappers enforce the same limits before requests are made.

## Important Notes

- This tool is designed as litigation intelligence and drafting assistance.
- It does not provide legal advice.
- Verified authorities must be stored with source information before they are used in final output.
- The system does not invent cases, statutes, rules, holdings, quotations, or authorities.
