from __future__ import annotations

import json
from typing import Any

from . import db
from .authority_validation import get_unverified_authorities, get_verified_authorities
from .intake import (
    get_case,
    list_action_items,
    list_claims,
    list_evidence,
    list_facts,
    list_parties,
)
from .research import get_research_logs


def _as_dict(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    if isinstance(record, dict):
        return dict(record)
    if hasattr(record, "to_dict"):
        return record.to_dict()
    try:
        return dict(record)
    except (TypeError, ValueError):
        return {}


def _item(item_type: str, title: str, summary: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_type": item_type,
        "title": title or f"Untitled {item_type.replace('_', ' ').title()}",
        "summary": summary or "No details entered.",
        "raw": raw,
    }


def build_case_profile(case_id: int, db_path: str | None = None) -> dict[str, Any]:
    case = get_case(case_id, db_path)
    if not case:
        return {"error": "Case not found.", "case_id": case_id, "items": []}

    case_data = _as_dict(case)
    parties = [_as_dict(record) for record in list_parties(case_id, db_path)]
    facts = [_as_dict(record) for record in list_facts(case_id, db_path)]
    claims = [_as_dict(record) for record in list_claims(case_id, db_path)]
    evidence = [_as_dict(record) for record in list_evidence(case_id, db_path)]
    actions = [_as_dict(record) for record in list_action_items(case_id, db_path)]
    verified_authorities = get_verified_authorities(case_id, db_path)
    unverified_authorities = get_unverified_authorities(case_id, db_path)
    research_logs = get_research_logs(case_id, db_path)
    audit_events = [_as_dict(record) for record in db.get_audit_events(db_path=db_path) if record.get("case_id") == case_id]
    documents = _get_documents(case_id, db_path)

    items: list[dict[str, Any]] = []
    items.append(_item("case", case_data.get("title", ""), case_data.get("description", ""), case_data))
    for party in parties:
        items.append(_item("party", party.get("name", ""), f"{party.get('role', '')} {party.get('notes', '')}".strip(), party))
    for fact in facts:
        items.append(_item("fact", fact.get("date", "") or "Fact", fact.get("fact_text", ""), fact))
    for claim in claims:
        items.append(_item("claim_or_defense", claim.get("claim_name", ""), claim.get("notes", "") or claim.get("jurisdiction_basis", ""), claim))
    for item_data in evidence:
        items.append(_item("evidence", item_data.get("title", ""), item_data.get("description", ""), item_data))
    for action in actions:
        items.append(_item("action_item", action.get("action_text", ""), action.get("notes", "") or action.get("due_date", ""), action))
    for authority in verified_authorities:
        items.append(_item("verified_authority", authority.get("title", ""), authority.get("citation", ""), authority))
    for authority in unverified_authorities:
        items.append(_item("unverified_authority", authority.get("title", ""), authority.get("citation", ""), authority))
    for log in research_logs:
        items.append(_item("research_log", log.get("query", ""), log.get("result_summary", ""), log))
    for event in audit_events:
        items.append(_item("audit_event", event.get("event_type", ""), event.get("description", ""), event))
    for document in documents:
        items.append(_item("document", document.get("title", ""), document.get("verification_status", ""), document))

    return {
        "case_id": case_id,
        "case": case_data,
        "parties": parties,
        "facts": facts,
        "claims": claims,
        "evidence": evidence,
        "action_items": actions,
        "verified_authorities": verified_authorities,
        "unverified_authorities": unverified_authorities,
        "research_logs": research_logs,
        "audit_events": audit_events,
        "documents": documents,
        "items": items,
    }


def build_ai_context(case_id: int, db_path: str | None = None) -> str:
    profile = build_case_profile(case_id, db_path)
    if profile.get("error"):
        return profile["error"]
    compact = {
        "case": profile["case"],
        "items": [
            {
                "item_type": item["item_type"],
                "title": item["title"],
                "summary": item["summary"],
            }
            for item in profile["items"]
        ],
        "verified_authorities": profile["verified_authorities"],
        "unverified_authorities": profile["unverified_authorities"],
    }
    return json.dumps(compact, indent=2, default=str)


def _get_documents(case_id: int, db_path: str | None = None) -> list[dict[str, Any]]:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE case_id = ? ORDER BY updated_at DESC", (case_id,))
        return [dict(row) for row in cursor.fetchall()]
