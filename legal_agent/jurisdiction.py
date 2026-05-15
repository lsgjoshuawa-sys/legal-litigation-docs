from __future__ import annotations
from typing import Any

from . import db
from .case_tracks import TRACK_TO_JURISDICTION, jurisdiction_for_track, normalize_legal_track

PROCEDURAL_RULES = {
    "California Superior Court": [
        "California Code of Civil Procedure",
        "California Rules of Court",
        "California Civil Code when applicable",
    ],
    "Federal Eastern District of California": [
        "Federal Rules of Civil Procedure",
        "Eastern District of California Local Rules",
        "Federal mortgage and servicing statutes when relevant",
    ],
    "Local law enforcement / local government civil dispute": [
        "California civil procedure",
        "California Government Claims Act concepts when relevant",
        "42 U.S.C. § 1983 and Monell analysis when applicable",
    ],
}


def classify_case(case_id: int, db_path: str | None = None) -> dict[str, Any]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        if not row:
            return {"classification": "unknown", "reason": "Case not found"}
        case = dict(row)
        track = normalize_legal_track(case.get("legal_track", ""))
        track_jurisdiction = jurisdiction_for_track(track)
        if track_jurisdiction and track_jurisdiction != "unclear":
            classification = track_jurisdiction
            reason = f"Procedure track explicitly set to {track}."
        elif case.get("court_name") and "Eastern District of California" in case["court_name"]:
            classification = "Federal Eastern District of California"
            reason = "Court name indicates Eastern District of California."
        elif case.get("court_name") and "Superior Court" in case["court_name"]:
            classification = "California Superior Court"
            reason = "Court name indicates California Superior Court."
        elif case.get("legal_track"):
            classification = TRACK_TO_JURISDICTION.get(track, track)
            reason = "Procedure track provided but not standard."
        else:
            classification = "unclear"
            reason = "Case information does not uniquely identify jurisdiction."
        from datetime import datetime, timezone
        cursor.execute(
            "UPDATE cases SET jurisdiction = ?, updated_at = ? WHERE id = ?",
            (classification, datetime.now(timezone.utc).isoformat(), case_id),
        )
        conn.commit()
        return {"classification": classification, "reason": reason}


def get_procedural_rules(case_id: int, db_path: str | None = None) -> dict[str, Any]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT jurisdiction FROM cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        if not row:
            return {"rules": [], "note": "Case not found"}
        jurisdiction = row["jurisdiction"] or "unclear"
        rules = PROCEDURAL_RULES.get(jurisdiction, [])
        if not rules:
            return {"rules": [], "note": "Jurisdiction unclear or not supported"}
        return {"rules": rules, "note": f"Using procedure set for {jurisdiction}."}
