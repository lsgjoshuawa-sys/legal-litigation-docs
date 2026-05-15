from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db
from .models import Authority
from .verification import validate_authority_payload


def _record_text(value: str | None, fallback: str, max_length: int = 5000) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return fallback
    return text[:max_length]


def _optional_text(value: str | None, max_length: int = 5000) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:max_length]


def add_authority(
    case_id: int,
    authority_type: str,
    title: str,
    citation: str,
    jurisdiction: str,
    court: str,
    year: int | None = None,
    source_url: str = "",
    source_text_excerpt: str = "",
    treatment_status: str = "unknown",
    treatment_notes: str = "",
    verified: bool = False,
    db_path: str | None = None,
) -> int:
    auth = Authority(
        case_id=case_id,
        authority_type=_record_text(authority_type, "unspecified", 255),
        title=_record_text(title, "Untitled Authority", 255),
        citation=_optional_text(citation, 500),
        jurisdiction=_optional_text(jurisdiction, 255),
        court=_optional_text(court, 255),
        year=year,
        source_url=_optional_text(source_url, 2048),
        source_text_excerpt=_optional_text(source_text_excerpt),
        treatment_status=_record_text(treatment_status, "unknown", 255),
        treatment_notes=_optional_text(treatment_notes),
        verified=verified,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO authorities (case_id, authority_type, title, citation, jurisdiction, court, year, source_url, source_text_excerpt, treatment_status, treatment_notes, verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                auth.case_id,
                auth.authority_type,
                auth.title,
                auth.citation,
                auth.jurisdiction,
                auth.court,
                auth.year,
                auth.source_url,
                auth.source_text_excerpt,
                auth.treatment_status,
                auth.treatment_notes,
                int(auth.verified),
                auth.created_at,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def verify_authority(authority_id: int, verified: bool | str | Path = True, db_path: str | None = None) -> bool:
    if isinstance(verified, (str, Path)) and db_path is None:
        db_path = str(verified)
        verified = True

    authority = get_authority(authority_id, db_path)
    if not authority:
        return False
    case_jurisdiction = None
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT jurisdiction FROM cases WHERE id = ?", (authority["case_id"],))
        case_row = cursor.fetchone()
        case_jurisdiction = dict(case_row)["jurisdiction"] if case_row else None
    checks = validate_authority_payload(authority, case_jurisdiction)
    should_verify = bool(verified)
    if should_verify and not checks.get("verified_ready", False):
        return False
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE authorities SET verified = ? WHERE id = ?", (1 if should_verify else 0, authority_id))
        conn.commit()
        return cursor.rowcount == 1


def get_authority(authority_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authorities WHERE id = ?", (authority_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_verified_authorities(case_id: int, db_path: str | None = None) -> list[dict[str, Any]]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authorities WHERE case_id = ? AND verified = 1 ORDER BY year DESC", (case_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_unverified_authorities(case_id: int, db_path: str | None = None) -> list[dict[str, Any]]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authorities WHERE case_id = ? AND verified = 0 ORDER BY created_at DESC", (case_id,))
        return [dict(row) for row in cursor.fetchall()]


def list_authorities(case_id: int, db_path: str | None = None) -> list[dict[str, Any]]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authorities WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
        return [dict(row) for row in cursor.fetchall()]
