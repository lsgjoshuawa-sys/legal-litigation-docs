from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db
from .authority_validation import add_authority
from .intake import add_action_item, add_evidence, add_fact
from .research import add_research_log


HANDLER_EVIDENCE = "Evidence"
HANDLER_AUTHORITY = "Authority Validation"
HANDLER_RESEARCH = "Legal Research"
HANDLER_ACTION = "Action Items & Due Dates"
HANDLER_FACTS = "Facts"
HANDLER_DRAFT = "Draft Generator"

HANDLER_CHOICES = [
    HANDLER_EVIDENCE,
    HANDLER_AUTHORITY,
    HANDLER_RESEARCH,
    HANDLER_ACTION,
    HANDLER_FACTS,
    HANDLER_DRAFT,
]

TEXT_PREVIEW_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".rtf"}
EXTRACTION_COMPATIBLE_SUFFIXES = TEXT_PREVIEW_SUFFIXES
EXTRACTION_COMPATIBLE_DESCRIPTION = "TXT, Markdown, CSV, JSON, XML, HTML, HTM, and RTF"

KEYWORDS = {
    HANDLER_AUTHORITY: [
        " v. ",
        "u.s.",
        "f.2d",
        "f.3d",
        "f.4th",
        "cal.",
        "cal.app",
        "statute",
        "code section",
        "rule of court",
        "frcp",
        "crc",
        "holding",
        "citation",
        "authority",
    ],
    HANDLER_DRAFT: [
        "complaint",
        "answer",
        "motion",
        "opposition",
        "declaration",
        "brief",
        "pleading",
        "draft",
        "memorandum of points",
        "request for judicial notice",
    ],
    HANDLER_ACTION: [
        "deadline",
        "due date",
        "task",
        "todo",
        "checklist",
        "calendar",
        "serve",
        "service deadline",
        "file by",
    ],
    HANDLER_RESEARCH: [
        "research",
        "memo",
        "issue presented",
        "legal standard",
        "analysis",
        "courtlistener",
        "secondary source",
        "research question",
    ],
    HANDLER_FACTS: [
        "timeline",
        "incident",
        "chronology",
        "witness",
        "statement",
        "narrative",
        "material fact",
        "fact summary",
    ],
    HANDLER_EVIDENCE: [
        "exhibit",
        "evidence",
        "receipt",
        "invoice",
        "contract",
        "email",
        "photo",
        "image",
        "video",
        "bodycam",
        "transcript",
        "record",
        "report",
    ],
}

EVIDENCE_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".tif",
    ".tiff",
    ".mp3",
    ".mp4",
    ".mov",
    ".wav",
    ".doc",
    ".docx",
}


@dataclass(frozen=True)
class TopicSuggestion:
    handler: str
    confidence: str
    reasons: list[str]


@dataclass(frozen=True)
class SubmissionResult:
    handler: str
    record_id: int
    message: str


def read_file_preview(file_path: str | Path, max_chars: int = 12000) -> str:
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        return ""
    if path.suffix.lower() not in TEXT_PREVIEW_SUFFIXES:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return ""


def is_data_extraction_compatible(file_path: str | Path) -> bool:
    return Path(file_path).expanduser().suffix.lower() in EXTRACTION_COMPATIBLE_SUFFIXES


def data_extraction_recommendation(file_path: str | Path) -> str:
    path = Path(file_path).expanduser()
    if is_data_extraction_compatible(path):
        return f"Data extraction is available for {path.suffix.lower() or 'this text file'} files."
    return (
        "Data extraction is only recommended for readable text files: "
        f"{EXTRACTION_COMPATIBLE_DESCRIPTION}. This file can still be routed and stored."
    )


def infer_document_topic(file_path: str | Path, preview_text: str = "") -> TopicSuggestion:
    path = Path(file_path).expanduser()
    searchable = f"{path.name}\n{preview_text}".lower()
    scores = {handler: 0 for handler in HANDLER_CHOICES}
    reasons: dict[str, list[str]] = {handler: [] for handler in HANDLER_CHOICES}

    for handler, keywords in KEYWORDS.items():
        for keyword in keywords:
            if keyword in searchable:
                scores[handler] += 1
                if len(reasons[handler]) < 4:
                    reasons[handler].append(f"matched '{keyword.strip()}'")

    suffix = path.suffix.lower()
    if suffix in EVIDENCE_SUFFIXES:
        scores[HANDLER_EVIDENCE] += 1
        reasons[HANDLER_EVIDENCE].append(f"{suffix or 'file'} commonly routes as evidence")

    if " v. " in searchable and any(marker in searchable for marker in ("u.s.", "f.3d", "cal.", "court")):
        scores[HANDLER_AUTHORITY] += 2
        reasons[HANDLER_AUTHORITY].append("case citation pattern detected")

    ranked = sorted(scores.items(), key=lambda item: (-item[1], HANDLER_CHOICES.index(item[0])))
    handler, score = ranked[0]
    if score <= 0:
        return TopicSuggestion(
            handler=HANDLER_EVIDENCE,
            confidence="low",
            reasons=["no strong topic signals; defaulting to Evidence for source preservation"],
        )
    confidence = "high" if score >= 3 else "medium"
    return TopicSuggestion(handler=handler, confidence=confidence, reasons=reasons[handler] or ["topic signal detected"])


def submit_file_to_handler(
    case_id: int,
    file_path: str | Path,
    handler: str,
    title: str = "",
    notes: str = "",
    preview_text: str = "",
    extract_data: bool = False,
    db_path: str | None = None,
) -> SubmissionResult:
    path = Path(file_path).expanduser()
    normalized_handler = handler if handler in HANDLER_CHOICES else HANDLER_EVIDENCE
    extracted = extract_case_details(preview_text) if extract_data and is_data_extraction_compatible(path) else {}
    display_title = title.strip() or _field_value(extracted, "title", "name") or path.stem or "Submitted File"
    summary = _submission_summary(path, notes, preview_text)

    if normalized_handler == HANDLER_EVIDENCE:
        record_id = add_evidence(
            case_id,
            title=display_title,
            evidence_type=_field_value(extracted, "evidence_type", "type") or _evidence_type_for_path(path),
            description=_field_value(extracted, "description", "summary") or summary,
            file_path=str(path),
            date_obtained=_field_value(extracted, "date_obtained", "date"),
            supports_claims_json=_field_value(extracted, "supports_claims", "claims") or "[]",
            admissibility_notes=_field_value(extracted, "admissibility_notes", "admissibility"),
            weakness_notes=_field_value(extracted, "weakness_notes", "weakness"),
            db_path=db_path,
        )
    elif normalized_handler == HANDLER_AUTHORITY:
        record_id = add_authority(
            case_id,
            authority_type=_field_value(extracted, "authority_type", "type") or _authority_type_for_text(path, preview_text),
            title=display_title,
            citation=_field_value(extracted, "citation"),
            jurisdiction=_field_value(extracted, "jurisdiction"),
            court=_field_value(extracted, "court"),
            year=_field_year(extracted),
            source_url=_field_value(extracted, "source_url", "url") or str(path),
            source_text_excerpt=_field_value(extracted, "excerpt", "source_text_excerpt") or preview_text[:5000],
            treatment_status=_field_value(extracted, "treatment_status", "treatment") or "unknown",
            treatment_notes=_field_value(extracted, "treatment_notes", "notes") or notes,
            verified=False,
            db_path=db_path,
        )
    elif normalized_handler == HANDLER_RESEARCH:
        record_id = add_research_log(
            case_id,
            query=_field_value(extracted, "query", "research_question", "issue") or display_title,
            source=_field_value(extracted, "source") or f"Submitted file: {path.name}",
            result_summary=_field_value(extracted, "result_summary", "summary", "analysis") or summary,
            authority_ids_json=_field_value(extracted, "authority_ids", "authority_ids_json") or "[]",
            db_path=db_path,
        )
    elif normalized_handler == HANDLER_ACTION:
        record_id = add_action_item(
            case_id,
            action_text=_field_value(extracted, "action_text", "action", "task") or f"Review submitted file: {display_title}",
            category=_field_value(extracted, "category") or "file review",
            due_date=_field_value(extracted, "due_date", "deadline"),
            dependency=_field_value(extracted, "dependency") or str(path),
            status=_field_value(extracted, "status") or "open",
            notes=_field_value(extracted, "notes") or summary,
            db_path=db_path,
        )
    elif normalized_handler == HANDLER_FACTS:
        record_id = add_fact(
            case_id,
            fact_text=_field_value(extracted, "fact_text", "fact") or preview_text.strip() or notes.strip() or f"Review factual content in {path.name}",
            date=_field_value(extracted, "date"),
            relevance=_field_value(extracted, "relevance") or f"Submitted file: {path.name}",
            db_path=db_path,
        )
    else:
        record_id = _save_imported_document(case_id, display_title, path, summary, preview_text, db_path, extracted)

    return SubmissionResult(
        handler=normalized_handler,
        record_id=record_id,
        message=f"Submitted '{path.name}' to {normalized_handler} as record {record_id}.",
    )


def _submission_summary(path: Path, notes: str, preview_text: str) -> str:
    parts = [
        "Submitted through File Submission.",
        f"File path: {path}",
    ]
    if notes.strip():
        parts.append(f"Notes: {notes.strip()}")
    if preview_text.strip():
        parts.append("Preview:")
        parts.append(preview_text.strip()[:5000])
    return "\n\n".join(parts)


def extract_case_details(preview_text: str) -> dict[str, str]:
    """Extract simple labeled fields from readable submitted file text."""
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in preview_text.splitlines():
        line = raw_line.strip()
        if not line:
            current_key = None
            continue
        match = re.match(r"^[\-*#\s]*([A-Za-z][A-Za-z0-9 _/-]{1,48})\s*[:=]\s*(.*)$", line)
        if match:
            key = _normalize_field_key(match.group(1))
            value = match.group(2).strip()
            if key and value:
                fields[key] = value
                current_key = key
            continue
        if current_key and len(fields[current_key]) < 4000:
            fields[current_key] = f"{fields[current_key]}\n{line}".strip()

    if "title" not in fields:
        first_line = _first_meaningful_line(preview_text)
        if first_line:
            fields["title"] = first_line[:255]
    if "citation" not in fields:
        citation = _find_citation(preview_text)
        if citation:
            fields["citation"] = citation
    return fields


def _normalize_field_key(raw_key: str) -> str:
    key = raw_key.strip().lower().replace("-", " ").replace("/", " ")
    key = re.sub(r"\s+", "_", key)
    aliases = {
        "name": "title",
        "document_title": "title",
        "evidence_type": "evidence_type",
        "date_obtained": "date_obtained",
        "supported_claims": "supports_claims",
        "admissibility_notes": "admissibility_notes",
        "weakness_notes": "weakness_notes",
        "authority_type": "authority_type",
        "source_url": "source_url",
        "source_text_excerpt": "source_text_excerpt",
        "treatment_status": "treatment_status",
        "treatment_notes": "treatment_notes",
        "research_question": "research_question",
        "result_summary": "result_summary",
        "authority_ids": "authority_ids",
        "authority_ids_json": "authority_ids_json",
        "action_text": "action_text",
        "due_date": "due_date",
        "fact_text": "fact_text",
        "document_type": "document_type",
    }
    return aliases.get(key, key)


def _field_value(fields: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = fields.get(key, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _field_year(fields: dict[str, str]) -> int | None:
    value = _field_value(fields, "year")
    if not value:
        return None
    match = re.search(r"\b(18|19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().strip("#").strip()
        if stripped:
            return stripped
    return ""


def _find_citation(text: str) -> str:
    patterns = [
        r"\b\d+\s+U\.S\.\s+\d+\b",
        r"\b\d+\s+F\.(?:2d|3d|4th)\s+\d+\b",
        r"\b\d+\s+Cal\.(?:App\.)?\w*\s+\d+\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def _evidence_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"png", "jpg", "jpeg", "gif", "tif", "tiff"}:
        return "image"
    if suffix in {"mp4", "mov"}:
        return "video"
    if suffix in {"mp3", "wav"}:
        return "audio"
    if suffix in {"txt", "md", "doc", "docx", "pdf", "rtf"}:
        return "document"
    return suffix or "file"


def _authority_type_for_text(path: Path, preview_text: str) -> str:
    searchable = f"{path.name}\n{preview_text}".lower()
    if any(term in searchable for term in ("statute", "code section", "u.s.c.", "civ. code", "penal code")):
        return "statute"
    if any(term in searchable for term in ("rule", "frcp", "crc")):
        return "rule"
    if " v. " in searchable:
        return "case"
    return "unspecified"


def _document_type_for_text(path: Path, preview_text: str) -> str:
    searchable = f"{path.name}\n{preview_text}".lower()
    for doc_type in [
        "complaint",
        "answer",
        "opposition",
        "declaration",
        "request for judicial notice",
        "motion outline",
        "motion",
        "brief",
    ]:
        if doc_type in searchable:
            return doc_type
    return "imported document"


def _save_imported_document(
    case_id: int,
    title: str,
    path: Path,
    summary: str,
    preview_text: str,
    db_path: str | None,
    extracted: dict[str, str] | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    extracted = extracted or {}
    document_type = _field_value(extracted, "document_type", "type") or _document_type_for_text(path, preview_text)
    draft_markdown = _field_value(extracted, "draft", "content", "summary") or summary
    verification_status = {
        "draft_status": "imported_source",
        "source_file": str(path),
        "requires_review": True,
    }
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents
                (case_id, document_type, title, outline_json, draft_markdown, verification_status,
                 vulnerability_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                document_type,
                title,
                json.dumps([]),
                draft_markdown,
                json.dumps(verification_status, sort_keys=True),
                "pending",
                now,
                now,
            ),
        )
        conn.commit()
        return cursor.lastrowid
