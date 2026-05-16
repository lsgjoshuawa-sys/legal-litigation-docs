from __future__ import annotations
from datetime import datetime, timezone
import json
from typing import Any, List, Optional

from . import db
from .case_folders import ensure_case_folder
from .case_tracks import normalize_legal_track
from .models import Case, Party, Fact, Claim, Evidence, ActionItem


def _record_text(value: str | None, fallback: str, max_length: int = 5000) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return fallback
    return text[:max_length]


def _optional_text(value: str | None, max_length: int = 5000) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:max_length]


def _record_date(value: str | None) -> str:
    return _optional_text(value, 64)


def _normalize_json_list(value: str | None) -> str:
    text = _optional_text(value)
    if not text:
        return "[]"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return json.dumps(parsed)
        return json.dumps([str(parsed)])
    except json.JSONDecodeError:
        return json.dumps([item.strip(" \t\r-*") for item in text.replace(",", "\n").splitlines() if item.strip(" \t\r-*")])


def create_case(
    title: str,
    description: str = "",
    legal_track: str = "",
    jurisdiction: str = "",
    court_name: str = "",
    court_level: str = "",
    district: str = "",
    judge: str = "",
    department: str = "",
    filing_status: str = "",
    db_path: str | None = None,
) -> int:
    title = _record_text(title, "Untitled Case", 255)
    case = Case(
        title=title,
        description=_optional_text(description),
        legal_track=normalize_legal_track(_optional_text(legal_track, 255)),
        jurisdiction=_optional_text(jurisdiction, 255),
        court_name=_optional_text(court_name, 255),
        court_level=_optional_text(court_level, 255),
        district=_optional_text(district, 255),
        judge=_optional_text(judge, 255),
        department=_optional_text(department, 255),
        filing_status=_optional_text(filing_status, 255),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cases (title, description, legal_track, jurisdiction, court_name, court_level, district,
                judge, department, filing_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.title,
                case.description,
                case.legal_track,
                case.jurisdiction,
                case.court_name,
                case.court_level,
                case.district,
                case.judge,
                case.department,
                case.filing_status,
                case.created_at.isoformat(),
                case.updated_at.isoformat(),
            ),
        )
        conn.commit()
        case_id = cursor.lastrowid
    ensure_case_folder(case_id, case.title, db_path=db_path)
    return case_id


def add_party(
    case_id: int,
    name: str,
    role: str = "",
    type: str = "",
    notes: str = "",
    db_path: str | None = None,
) -> int:
    party = Party(
        case_id=case_id,
        name=_record_text(name, "Unnamed Party", 255),
        role=_optional_text(role, 255),
        type=_optional_text(type, 255),
        notes=_optional_text(notes),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO parties (case_id, name, role, type, notes) VALUES (?, ?, ?, ?, ?)" ,
            (party.case_id, party.name, party.role, party.type, party.notes),
        )
        conn.commit()
        return cursor.lastrowid


def add_fact(
    case_id: int,
    fact_text: str,
    date: str = "",
    source_evidence_id: int | None = None,
    relevance: str = "",
    db_path: str | None = None,
) -> int:
    fact = Fact(
        case_id=case_id,
        date=_record_date(date),
        fact_text=_record_text(fact_text, "Untitled fact note"),
        source_evidence_id=source_evidence_id,
        relevance=_optional_text(relevance, 255),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO facts (case_id, date, fact_text, source_evidence_id, relevance, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fact.case_id, fact.date, fact.fact_text, fact.source_evidence_id, fact.relevance, fact.created_at.isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def add_claim(
    case_id: int,
    claim_name: str,
    claim_type: str = "",
    jurisdiction_basis: str = "",
    required_elements_json: str = "[]",
    status: str = "",
    notes: str = "",
    db_path: str | None = None,
) -> int:
    required_elements_json = _normalize_json_list(required_elements_json)
    claim = Claim(
        case_id=case_id,
        claim_name=_record_text(claim_name, "Unspecified Claim or Defense", 255),
        claim_type=_optional_text(claim_type, 255),
        jurisdiction_basis=_optional_text(jurisdiction_basis, 1000),
        required_elements_json=required_elements_json,
        status=_optional_text(status, 255),
        notes=_optional_text(notes),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO claims (case_id, claim_name, claim_type, jurisdiction_basis, required_elements_json, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                claim.case_id,
                claim.claim_name,
                claim.claim_type,
                claim.jurisdiction_basis,
                claim.required_elements_json,
                claim.status,
                claim.notes,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def add_evidence(
    case_id: int,
    title: str,
    evidence_type: str = "",
    description: str = "",
    file_path: str = "",
    date_obtained: str = "",
    supports_claims_json: str = "[]",
    admissibility_notes: str = "",
    weakness_notes: str = "",
    db_path: str | None = None,
) -> int:
    supports_claims_json = _normalize_json_list(supports_claims_json)
    evidence = Evidence(
        case_id=case_id,
        title=_record_text(title, "Untitled Evidence", 255),
        evidence_type=_optional_text(evidence_type, 255),
        description=_optional_text(description),
        file_path=_optional_text(file_path, 1000),
        date_obtained=_record_date(date_obtained),
        supports_claims_json=supports_claims_json,
        admissibility_notes=_optional_text(admissibility_notes),
        weakness_notes=_optional_text(weakness_notes),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO evidence (case_id, title, evidence_type, description, file_path, date_obtained, supports_claims_json, admissibility_notes, weakness_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence.case_id,
                evidence.title,
                evidence.evidence_type,
                evidence.description,
                evidence.file_path,
                evidence.date_obtained,
                evidence.supports_claims_json,
                evidence.admissibility_notes,
                evidence.weakness_notes,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def add_action_item(
    case_id: int,
    action_text: str,
    category: str = "",
    due_date: str = "",
    dependency: str = "",
    status: str = "open",
    notes: str = "",
    db_path: str | None = None,
) -> int:
    action_item = ActionItem(
        case_id=case_id,
        action_text=_record_text(action_text, "Untitled Action Item", 1000),
        category=_optional_text(category, 255),
        due_date=_record_date(due_date),
        dependency=_optional_text(dependency, 1000),
        status=_record_text(status, "open", 255),
        notes=_optional_text(notes),
    )
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO action_items (case_id, action_text, category, due_date, dependency, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                action_item.case_id,
                action_item.action_text,
                action_item.category,
                action_item.due_date,
                action_item.dependency,
                action_item.status,
                action_item.notes,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def request_due_dates(case_id: int, db_path: str | None = None) -> List[ActionItem]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_items WHERE case_id = ?", (case_id,))
        rows = cursor.fetchall()
        updated_items: List[ActionItem] = []
        for row in rows:
            item = db._row_to_action_item(row)
            if not item.due_date:
                print(f"Action item #{item.id}: {item.action_text}")
                due_date = input("Enter due date (YYYY-MM-DD) or leave blank for unknown: ").strip()
                if due_date:
                    cursor.execute("UPDATE action_items SET due_date = ? WHERE id = ?", (due_date, item.id))
                    item.due_date = due_date
                else:
                    cursor.execute("UPDATE action_items SET due_date = ? WHERE id = ?", ("unknown", item.id))
                    item.due_date = "unknown"
            updated_items.append(item)
        conn.commit()
        return updated_items


def generate_timeline(case_id: int, db_path: str | None = None) -> List[ActionItem]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_items WHERE case_id = ? ORDER BY due_date ASC", (case_id,))
        return [db._row_to_action_item(row) for row in cursor.fetchall()]


def get_case(case_id: int, db_path: str | None = None) -> Optional[Case]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        return db._row_to_case(row) if row else None


def list_case_ids(db_path: str | None = None) -> list[int]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cases")
        return [row["id"] for row in cursor.fetchall()]


def list_cases(db_path: str | None = None) -> List[Case]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases ORDER BY updated_at DESC")
        return [db._row_to_case(row) for row in cursor.fetchall()]


def list_parties(case_id: int, db_path: str | None = None) -> List[Party]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM parties WHERE case_id = ?", (case_id,))
        return [db._row_to_party(row) for row in cursor.fetchall()]


def list_facts(case_id: int, db_path: str | None = None) -> List[Fact]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM facts WHERE case_id = ? ORDER BY date DESC", (case_id,))
        return [db._row_to_fact(row) for row in cursor.fetchall()]


def list_claims(case_id: int, db_path: str | None = None) -> List[Claim]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM claims WHERE case_id = ? ORDER BY id", (case_id,))
        return [db._row_to_claim(row) for row in cursor.fetchall()]


def list_evidence(case_id: int, db_path: str | None = None) -> List[Evidence]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE case_id = ? ORDER BY id", (case_id,))
        return [db._row_to_evidence(row) for row in cursor.fetchall()]


def list_action_items(case_id: int, db_path: str | None = None) -> List[ActionItem]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_items WHERE case_id = ? ORDER BY due_date ASC", (case_id,))
        return [db._row_to_action_item(row) for row in cursor.fetchall()]


def update_case(
    case_id: int,
    title: str,
    description: str,
    legal_track: str,
    jurisdiction: str,
    court_name: str,
    court_level: str,
    district: str,
    judge: str,
    department: str,
    filing_status: str,
    db_path: str | None = None,
) -> bool:
    title = _record_text(title, "Untitled Case", 255)
    updated_at = datetime.now(timezone.utc).isoformat()
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cases SET title = ?, description = ?, legal_track = ?, jurisdiction = ?, court_name = ?, court_level = ?, district = ?, judge = ?, department = ?, filing_status = ?, updated_at = ? WHERE id = ?",
            (
                title,
                _optional_text(description),
                normalize_legal_track(_optional_text(legal_track, 255)),
                _optional_text(jurisdiction, 255),
                _optional_text(court_name, 255),
                _optional_text(court_level, 255),
                _optional_text(district, 255),
                _optional_text(judge, 255),
                _optional_text(department, 255),
                _optional_text(filing_status, 255),
                updated_at,
                case_id,
            ),
        )
        conn.commit()
        updated = cursor.rowcount == 1
    if updated:
        ensure_case_folder(case_id, title, db_path=db_path)
    return updated


def update_party(
    party_id: int,
    name: str,
    role: str,
    type: str,
    notes: str,
    db_path: str | None = None,
) -> bool:
    name = _record_text(name, "Unnamed Party", 255)
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE parties SET name = ?, role = ?, type = ?, notes = ? WHERE id = ?",
            (name, _optional_text(role, 255), _optional_text(type, 255), _optional_text(notes), party_id),
        )
        conn.commit()
        return cursor.rowcount == 1


def delete_party(party_id: int, db_path: str | None = None) -> bool:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM parties WHERE id = ?", (party_id,))
        conn.commit()
        return cursor.rowcount == 1


def update_fact(
    fact_id: int,
    date: str,
    fact_text: str,
    source_evidence_id: int | None,
    relevance: str,
    db_path: str | None = None,
) -> bool:
    fact_text = _record_text(fact_text, "Untitled fact note")
    date = _record_date(date)
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE facts SET date = ?, fact_text = ?, source_evidence_id = ?, relevance = ? WHERE id = ?",
            (date, fact_text, source_evidence_id, _optional_text(relevance, 255), fact_id),
        )
        conn.commit()
        return cursor.rowcount == 1


def delete_fact(fact_id: int, db_path: str | None = None) -> bool:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        conn.commit()
        return cursor.rowcount == 1


def update_claim(
    claim_id: int,
    claim_name: str,
    claim_type: str,
    jurisdiction_basis: str,
    required_elements_json: str,
    status: str,
    notes: str,
    db_path: str | None = None,
) -> bool:
    claim_name = _record_text(claim_name, "Unspecified Claim or Defense", 255)
    required_elements_json = _normalize_json_list(required_elements_json)
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE claims SET claim_name = ?, claim_type = ?, jurisdiction_basis = ?, required_elements_json = ?, status = ?, notes = ? WHERE id = ?",
            (claim_name, _optional_text(claim_type, 255), _optional_text(jurisdiction_basis, 1000), required_elements_json, _optional_text(status, 255), _optional_text(notes), claim_id),
        )
        conn.commit()
        return cursor.rowcount == 1


def delete_claim(claim_id: int, db_path: str | None = None) -> bool:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
        conn.commit()
        return cursor.rowcount == 1


def update_evidence(
    evidence_id: int,
    title: str,
    evidence_type: str,
    description: str,
    file_path: str,
    date_obtained: str,
    supports_claims_json: str,
    admissibility_notes: str,
    weakness_notes: str,
    db_path: str | None = None,
) -> bool:
    title = _record_text(title, "Untitled Evidence", 255)
    date_obtained = _record_date(date_obtained)
    supports_claims_json = _normalize_json_list(supports_claims_json)
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE evidence SET title = ?, evidence_type = ?, description = ?, file_path = ?, date_obtained = ?, supports_claims_json = ?, admissibility_notes = ?, weakness_notes = ? WHERE id = ?",
            (title, _optional_text(evidence_type, 255), _optional_text(description), _optional_text(file_path, 1000), date_obtained, supports_claims_json, _optional_text(admissibility_notes), _optional_text(weakness_notes), evidence_id),
        )
        conn.commit()
        return cursor.rowcount == 1


def delete_evidence(evidence_id: int, db_path: str | None = None) -> bool:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM evidence WHERE id = ?", (evidence_id,))
        conn.commit()
        return cursor.rowcount == 1


def update_action_item(
    action_item_id: int,
    action_text: str,
    category: str,
    due_date: str,
    dependency: str,
    status: str,
    notes: str,
    db_path: str | None = None,
) -> bool:
    action_text = _record_text(action_text, "Untitled Action Item", 1000)
    due_date = _record_date(due_date)
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE action_items SET action_text = ?, category = ?, due_date = ?, dependency = ?, status = ?, notes = ? WHERE id = ?",
            (action_text, _optional_text(category, 255), due_date, _optional_text(dependency, 1000), _record_text(status, "open", 255), _optional_text(notes), action_item_id),
        )
        conn.commit()
        return cursor.rowcount == 1


def delete_action_item(action_item_id: int, db_path: str | None = None) -> bool:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM action_items WHERE id = ?", (action_item_id,))
        conn.commit()
        return cursor.rowcount == 1
