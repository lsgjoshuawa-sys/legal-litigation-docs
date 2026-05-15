from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any

from . import db
from .authority_validation import get_verified_authorities
from .courtlistener_access import validate_output_citations
from .models import Document
from .observability import performance_checkpoint

DOCUMENT_OUTLINES = {
    "complaint": [
        "Caption",
        "Jurisdiction and Venue",
        "Parties",
        "Statement of Facts",
        "Causes of Action",
        "Prayer for Relief",
    ],
    "answer": [
        "Caption",
        "Admissions and Denials",
        "Affirmative Defenses",
        "Prayer for Relief",
    ],
    "opposition": [
        "Caption",
        "Introduction",
        "Summary of Facts",
        "Legal Standards",
        "Argument",
        "Conclusion",
    ],
    "demurrer opposition": [
        "Caption",
        "Procedural Posture",
        "Standard of Review",
        "Argument Against Demurrer",
        "Conclusion",
    ],
    "motion opposition": [
        "Caption",
        "Introduction",
        "Statement of Facts",
        "Legal Standard",
        "Argument",
        "Conclusion",
    ],
    "declaration": [
        "Caption",
        "Declarant Introduction",
        "Statement of Facts",
        "Signature Block",
    ],
    "request for judicial notice": [
        "Caption",
        "Introduction",
        "Request for Judicial Notice",
        "Conclusion",
    ],
    "motion outline": [
        "Caption",
        "Issue Presented",
        "Standard of Review",
        "Arguments",
        "Relief Requested",
    ],
    "federal motion-to-dismiss opposition outline": [
        "Caption",
        "Legal Standards",
        "Plaintiff Allegations",
        "Argument Against Dismissal",
        "Conclusion",
    ],
    "filing checklist": [
        "Case Summary",
        "Verified Authorities",
        "Evidence Support",
        "Service Requirements",
        "Filing Requirements",
    ],
}


def _fetch_rows(cursor: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def generate_outline(case_id: int, document_type: str, db_path: str | None = None) -> dict[str, Any]:
    document_type_lower = document_type.strip().lower() or "complaint"
    outline = DOCUMENT_OUTLINES.get(document_type_lower, ["Caption", "Introduction", "Conclusion"])
    title = f"{document_type_lower.title()} Outline"
    return {"document_type": document_type_lower, "title": title, "outline": outline}


def _build_draft_text(case: dict[str, Any], document_type: str, verified_authorities: list[dict[str, Any]]) -> str:
    document_type_lower = document_type.strip().lower() or "complaint"
    outline = DOCUMENT_OUTLINES.get(document_type_lower, ["Caption", "Introduction", "Conclusion"])
    lines = [f"# {document_type_lower.title()} Draft", ""]
    if case.get("title"):
        lines.append(f"**Case:** {case['title']}")
    lines.append(f"**Jurisdiction:** {case.get('jurisdiction', 'Unknown')}")
    lines.append("")
    for section in outline:
        lines.append(f"## {section}")
        if section == "Caption":
            lines.append("[Insert court caption, case number, and parties.]")
        elif section == "Jurisdiction and Venue":
            lines.append("[Insert jurisdictional basis and venue facts with verified rule references.]")
        elif section == "Parties":
            lines.append("[Insert plaintiff and defendant party descriptions and capacities.]")
        elif section == "Statement of Facts":
            lines.append("[Insert verified case facts and evidence summaries.]")
        elif section == "Causes of Action":
            lines.append("[List each claim with a short statement of why facts support it.]")
        elif section == "Prayer for Relief":
            lines.append("[Insert requested relief and damages categories.]")
        elif section == "Admissions and Denials":
            lines.append("[Insert specific responses to complaint allegations.]")
        elif section == "Affirmative Defenses":
            lines.append("[Insert legally recognized affirmative defenses and supporting facts.]")
        elif section in {"Introduction", "Summary of Facts", "Argument", "Conclusion", "Legal Standard", "Standard of Review", "Procedural Posture", "Issue Presented", "Relief Requested", "Request for Judicial Notice", "Declarant Introduction", "Signature Block"}:
            lines.append(f"[Insert {section.lower()} content based on verified facts and authorities.]")
        else:
            lines.append("[Insert section content.]")
        lines.append("")
    if verified_authorities:
        lines.append("## Verified Authorities")
        for authority in verified_authorities:
            lines.append(f"- [{authority['id']}] {authority['title']} ({authority['citation']})")
        lines.append("")
    else:
        lines.append("## Verified Authorities")
        lines.append("No verified authorities are currently available; fill in with verified sources before final submission.")
        lines.append("")
    lines.append("## Disclaimer")
    lines.append("This draft is a legal operations drafting assist tool output, not legal advice. Verify every authority and fact before filing.")
    return "\n".join(lines)


def save_document(case_id: int, document_type: str, db_path: str | None = None) -> dict[str, Any]:
    with performance_checkpoint(
        "save_document",
        context={"case_id": case_id, "document_type": document_type},
        slow_ms=1000,
    ):
        document_type = document_type.strip() if isinstance(document_type, str) else ""
        if not document_type:
            document_type = "complaint"
        case = _get_case(case_id, db_path)
        if not case:
            return {"error": "Case not found."}
        verified_authorities = get_verified_authorities(case_id, db_path)
        outline_data = generate_outline(case_id, document_type, db_path)
        draft_text = _build_draft_text(case, document_type, verified_authorities)
        citation_validation = validate_output_citations(verified_authorities)
        now = datetime.now(timezone.utc).isoformat()
        with db.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO documents (case_id, document_type, title, outline_json, draft_markdown, verification_status, vulnerability_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    case_id,
                    document_type,
                    outline_data["title"],
                    json.dumps(outline_data["outline"]),
                    draft_text,
                    json.dumps(
                        {
                            "draft_status": "draft",
                            "courtlistener": citation_validation,
                        },
                        sort_keys=True,
                    ),
                    "pending",
                    now,
                    now,
                ),
            )
            conn.commit()
            return {
                "document_id": cursor.lastrowid,
                "draft_text": draft_text,
                "citation_validation": citation_validation,
            }


def get_document(document_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def _get_case(case_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
