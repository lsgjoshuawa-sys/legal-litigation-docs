# Disaster Recovery Procedures

## Recovery Objectives

- Database recovery point objective: last successful backup.
- Database recovery time objective: restore SQLite file and verify health before reopening the app.
- Logs are useful for diagnosis but should not be treated as the source of record.

## Backup Procedure

1. Close the GUI and stop CLI jobs that write to the database.
2. Copy the SQLite database to encrypted backup storage.
3. Record the backup timestamp, application version, and database path.
4. Periodically test restoring a backup into a temporary location.

Example:

```bash
sqlite3 /var/lib/legal_agent/legal_agent.db ".backup '/secure-backups/legal_agent-YYYYMMDD.db'"
```

## Restore Procedure

1. Stop the application.
2. Preserve the damaged database for forensic review.
3. Restore the selected backup to the configured database path.
4. Run a health check:

```bash
python -c "from legal_agent.db import check_db_health; raise SystemExit(0 if check_db_health('/var/lib/legal_agent/legal_agent.db') else 1)"
```

5. Open the application against the restored database.
6. Review recent audit logs, authority records, documents, and exports for missing work since the backup.

## Incident Response

- If an API key is exposed, revoke it immediately and create a replacement in the secret manager.
- If client data is exposed, preserve logs, identify affected records, and follow the governing notification process.
- If the database is corrupted, restore from the most recent clean backup and retain the corrupted file for analysis.
- If generated legal content is suspected to contain unverified authority, mark it draft-only and re-run authority validation before use.

## Validation After Recovery

- Confirm `check_db_health(...)` returns `True`.
- Confirm the GUI starts and loads cases.
- Confirm a test export works in a temporary folder.
- Confirm OpenAI calls fail gracefully when the API key is absent or invalid.
- Run `python -m unittest discover tests` before returning the system to production use.
