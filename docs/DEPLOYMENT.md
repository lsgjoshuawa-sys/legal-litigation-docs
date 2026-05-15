# Deployment Guide

## Runtime

- Use Python 3.12 or newer.
- Create an isolated virtual environment for each deployment.
- Install from the project root with `python -m pip install .`.
- Run `python -m legal_agent.cli init-db --db /path/to/legal_agent.db` before first use.

## Configuration

Create a `.env` file or set equivalent environment variables in the host secret manager:

```bash
OPENAI_API_KEY=replace-with-managed-secret
LEGAL_AGENT_OPENAI_MODEL=gpt-4o-mini
LEGAL_AGENT_OPENAI_MAX_REQUESTS_PER_MINUTE=20
COURTLISTENER_ENABLED=false
COURTLISTENER_API_TOKEN=
COURTLISTENER_BASE_URL=https://www.courtlistener.com/api/rest/v4
LEGAL_AGENT_LOG_LEVEL=INFO
LEGAL_AGENT_LOG_DIR=/var/log/legal_agent
DATABASE_PATH=/var/lib/legal_agent/legal_agent.db
```

Do not commit `.env`, `.Tenv`, SQLite databases, logs, exports containing client data, or local config files.

## Security Checklist

- Store `OPENAI_API_KEY` in environment variables or a managed secret store.
- Rotate any API key that has been pasted into source files, chat, tickets, or logs.
- Restrict filesystem permissions on the database, logs, and export folders to authorized users only.
- Back up the SQLite database before upgrades.
- Verify that logs do not contain API keys, privileged communications, sealed records, or full client secrets.
- Keep authority verification enabled before using generated drafts in filings.
- Use a writable log directory and monitor `legal_agent.log` for API, database, and validation errors.
- Confirm outbound network access is limited to approved API endpoints.
- Keep CourtListener disabled unless a token is configured and users need explicit legal research/citation lookup.
- Run the full test suite before each release: `HOME=/tmp/legal-agent-home python -m unittest discover tests`.

## Release Steps

1. Install dependencies in a clean virtual environment.
2. Configure environment variables or `.env`.
3. Initialize or migrate the SQLite database.
4. Run targeted tests for changed modules.
5. Run the full unittest suite.
6. Start the CLI or GUI with a non-production test case.
7. Confirm database health, logging, and OpenAI error handling.
8. Back up the production database.
9. Deploy the package and restart the application.
