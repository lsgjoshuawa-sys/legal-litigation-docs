from __future__ import annotations
import json
from typing import Any

from . import db
from .models import Claim, Evidence


def _fetch_rows(cursor: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def get_claim(case_id: int, claim_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM claims WHERE id = ? AND case_id = ?", (claim_id, case_id))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_evidence_for_case(case_id: int, db_path: str | None = None) -> list[Evidence]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE case_id = ?", (case_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        return [Evidence(**row) for row in rows]


def element_checklist(case_id: int, claim_id: int, db_path: str | None = None) -> dict[str, Any]:
    claim_row = get_claim(case_id, claim_id, db_path)
    if not claim_row:
        return {"error": "Claim not found"}
    claim = Claim(**claim_row)
    required = claim.required_elements()
    evidence_items = get_evidence_for_case(case_id, db_path)
    supported: list[str] = []
    supplemental: list[str] = []
    for element in required:
        for item in evidence_items:
            supports = [s.lower() for s in item.supports_claims()]
            if element.lower() in supports or element.lower() in item.description.lower():
                supported.append(element)
                break
    supported = list(dict.fromkeys(supported))
    missing = [element for element in required if element not in supported]
    for item in evidence_items:
        if claim.claim_name.lower() in [s.lower() for s in item.supports_claims()] and item.description:
            description = f"{item.title}: {item.description}"
            if description not in supplemental:
                supplemental.append(description)
    weaknesses = []
    if missing:
        weaknesses.append("Required elements with no clear evidence support.")
    for item in evidence_items:
        if item.weakness_notes:
            weaknesses.append(f"Evidence weakness: {item.weakness_notes}")
    return {
        "claim_id": claim_id,
        "claim_name": claim.claim_name,
        "required_elements": required,
        "supported_elements": supported,
        "missing_elements": missing,
        "supplemental_items": supplemental,
        "weaknesses": weaknesses,
    }


def evidence_review(case_id: int, db_path: str | None = None) -> dict[str, Any]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM claims WHERE case_id = ?", (case_id,))
        claim_rows = [dict(row) for row in cursor.fetchall()]
    review = []
    for claim_row in claim_rows:
        checklist = element_checklist(case_id, claim_row["id"], db_path)
        review.append(checklist)
    return {
        "case_id": case_id,
        "claim_reviews": review,
    }
