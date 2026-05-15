from __future__ import annotations
from . import db

VALID_TREATMENTS = [
    "controlling",
    "persuasive",
    "distinguished",
    "criticized",
    "overruled",
    "partially overruled",
    "superseded",
    "vacated",
    "unknown",
]


def set_treatment_status(authority_id: int, treatment_status: str, treatment_notes: str = "", db_path: str | None = None) -> bool:
    status = treatment_status.strip().lower()
    if status not in VALID_TREATMENTS:
        raise ValueError(f"Unsupported treatment status: {treatment_status}")
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE authorities SET treatment_status = ?, treatment_notes = ? WHERE id = ?",
            (status, treatment_notes, authority_id),
        )
        conn.commit()
        return cursor.rowcount == 1


def get_treatment_status(authority_id: int, db_path: str | None = None) -> dict[str, str] | None:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT treatment_status, treatment_notes FROM authorities WHERE id = ?", (authority_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
