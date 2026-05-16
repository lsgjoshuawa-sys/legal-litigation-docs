from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any

from . import db
from .models import ResearchLog


def _record_text(value: str | None, fallback: str, max_length: int = 5000) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return fallback
    return text[:max_length]


def _optional_text(value: str | None, max_length: int = 5000) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:max_length]


def add_research_log(
    case_id: int,
    query: str,
    source: str,
    result_summary: str,
    authority_ids_json: str = "[]",
    db_path: str | None = None,
) -> int:
    query = _record_text(query, "Untitled Research Note", 1000)
    source = _record_text(source, "unspecified", 255)
    result_summary = _record_text(result_summary, "No summary entered.")
    try:
        json.loads(authority_ids_json)
    except json.JSONDecodeError:
        authority_ids_json = json.dumps(
            [item.strip(" \t\r-*") for item in authority_ids_json.replace(",", "\n").splitlines() if item.strip(" \t\r-*")]
        )
    log = ResearchLog(
        case_id=case_id,
        query=query,
        source=source,
        result_summary=result_summary,
        authority_ids_json=authority_ids_json,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO research_logs (case_id, query, source, result_summary, authority_ids_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                log.case_id,
                log.query,
                log.source,
                log.result_summary,
                log.authority_ids_json,
                log.created_at,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_research_logs(case_id: int, db_path: str | None = None) -> list[dict[str, Any]]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM research_logs WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
