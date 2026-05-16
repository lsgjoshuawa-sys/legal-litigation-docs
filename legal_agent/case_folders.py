from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db
from .logger import get_logger
from .openai_client import DEFAULT_MODEL, _chat_completion, load_dotenv

logger = get_logger(__name__)

SECTION_FOLDERS = [
    "00_case_intake",
    "01_file_submission",
    "02_parties",
    "03_facts",
    "04_claims_defenses",
    "05_evidence",
    "06_action_items_due_dates",
    "07_litigation_timeline",
    "08_jurisdiction_classifier",
    "09_procedural_rules",
    "10_legal_research",
    "11_courtlistener_research",
    "12_authority_validation",
    "13_citation_treatment_checker",
    "14_claim_element_checklist",
    "15_evidence_sufficiency_review",
    "16_document_strategy",
]

SYSTEM_FOLDERS = ["_processed", "_failed", "_quarantine", "_manifest"]

SECTION_LABELS = {
    "00_case_intake": "Case Intake",
    "01_file_submission": "File Submission",
    "02_parties": "Parties",
    "03_facts": "Facts",
    "04_claims_defenses": "Claims / Defenses",
    "05_evidence": "Evidence",
    "06_action_items_due_dates": "Action Items & Due Dates",
    "07_litigation_timeline": "Litigation Timeline",
    "08_jurisdiction_classifier": "Jurisdiction Classifier",
    "09_procedural_rules": "Procedural Rules",
    "10_legal_research": "Legal Research",
    "11_courtlistener_research": "CourtListener Research",
    "12_authority_validation": "Authority Validation",
    "13_citation_treatment_checker": "Citation Treatment Checker",
    "14_claim_element_checklist": "Claim Element Checklist",
    "15_evidence_sufficiency_review": "Evidence Sufficiency Review",
    "16_document_strategy": "Document Strategy",
}

TEXT_EXTRACTION_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".rtf",
}

COMMON_LEGAL_FILE_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".tif",
    ".tiff",
    ".heic",
    ".mp3",
    ".mp4",
    ".mov",
    ".wav",
}

SUPPORTED_SUFFIXES = TEXT_EXTRACTION_SUFFIXES | COMMON_LEGAL_FILE_SUFFIXES

SUSPICIOUS_SUFFIXES = {
    ".app",
    ".bat",
    ".cmd",
    ".com",
    ".deb",
    ".dll",
    ".dmg",
    ".exe",
    ".jar",
    ".js",
    ".msi",
    ".pkg",
    ".ps1",
    ".py",
    ".pyw",
    ".rpm",
    ".scr",
    ".sh",
    ".vbs",
}

SYSTEM_FILE_NAMES = {
    ".ds_store",
    "desktop.ini",
    "thumbs.db",
    "ehthumbs.db",
}

MAX_TEXT_CHARS = 12000
MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024

EXTRACTION_KEYS = [
    "summary",
    "key_facts",
    "parties_mentioned",
    "dates_and_deadlines",
    "evidence_references",
    "claims_or_defenses_mentioned",
    "jurisdiction_clues",
    "procedural_issues",
    "legal_authorities_cited",
    "action_items",
    "confidence_score",
    "extraction_warnings",
    "recommended_destination_section",
]


@dataclass
class ScanResult:
    case_count: int = 0
    scanned_files: int = 0
    new_files: int = 0
    skipped_existing: int = 0
    duplicate_files: int = 0
    extracted_files: int = 0
    pending_extractions: int = 0
    quarantined_files: int = 0
    failed_files: int = 0
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "ScanResult") -> None:
        self.case_count += other.case_count
        self.scanned_files += other.scanned_files
        self.new_files += other.new_files
        self.skipped_existing += other.skipped_existing
        self.duplicate_files += other.duplicate_files
        self.extracted_files += other.extracted_files
        self.pending_extractions += other.pending_extractions
        self.quarantined_files += other.quarantined_files
        self.failed_files += other.failed_files
        for warning in other.warnings:
            if warning not in self.warnings:
                self.warnings.append(warning)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "scanned_files": self.scanned_files,
            "new_files": self.new_files,
            "skipped_existing": self.skipped_existing,
            "duplicate_files": self.duplicate_files,
            "extracted_files": self.extracted_files,
            "pending_extractions": self.pending_extractions,
            "quarantined_files": self.quarantined_files,
            "failed_files": self.failed_files,
            "warnings": list(self.warnings),
        }

    def summary(self) -> str:
        parts = [
            f"{self.case_count} case folders",
            f"{self.scanned_files} files scanned",
            f"{self.new_files} new",
            f"{self.extracted_files} extracted",
            f"{self.pending_extractions} pending",
            f"{self.duplicate_files} duplicates",
            f"{self.quarantined_files} quarantined",
            f"{self.failed_files} failed",
        ]
        return ", ".join(parts)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cases_root(db_path: str | Path | None = None) -> Path:
    configured = os.getenv("LEGAL_AGENT_CASES_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if db_path:
        database_path = Path(db_path).expanduser()
        return database_path.parent / f"{database_path.stem}_cases"
    return Path.cwd() / "cases"


def safe_case_title(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", title.strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = "untitled_case"
    return cleaned[:80]


def case_folder_name(case_id: int, title: str) -> str:
    return f"{case_id}_{safe_case_title(title)}"


def case_directory(case_id: int, title: str, db_path: str | Path | None = None, create: bool = True) -> Path:
    root = cases_root(db_path)
    root.mkdir(parents=True, exist_ok=True)
    prefix = f"{case_id}_"
    existing = sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith(prefix))
    path = existing[0] if existing else root / case_folder_name(case_id, title)
    if create:
        ensure_case_folder(case_id, title, db_path=db_path, case_dir=path)
    return path


def ensure_case_folder(
    case_id: int,
    title: str,
    db_path: str | Path | None = None,
    case_dir: Path | None = None,
) -> Path:
    path = case_dir or case_directory(case_id, title, db_path=db_path, create=False)
    path.mkdir(parents=True, exist_ok=True)
    for folder in SECTION_FOLDERS + SYSTEM_FOLDERS:
        (path / folder).mkdir(parents=True, exist_ok=True)

    manifest_dir = path / "_manifest"
    for filename in ("files.jsonl", "extractions.jsonl", "errors.jsonl"):
        (manifest_dir / filename).touch(exist_ok=True)

    case_index = manifest_dir / "case.json"
    case_index.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "case_title": title,
                "case_directory": str(path),
                "section_folders": SECTION_FOLDERS,
                "system_folders": SYSTEM_FOLDERS,
                "updated_at": utc_now(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def manifest_paths(case_dir: Path) -> dict[str, Path]:
    manifest_dir = case_dir / "_manifest"
    return {
        "files": manifest_dir / "files.jsonl",
        "extractions": manifest_dir / "extractions.jsonl",
        "errors": manifest_dir / "errors.jsonl",
    }


def calculate_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    target = Path(path)
    if not target.exists():
        return records
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSONL line in %s", target)
                    continue
                if isinstance(parsed, dict):
                    records.append(parsed)
    except OSError as exc:
        logger.warning("Unable to read manifest %s: %s", target, exc)
    return records


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_sidecar(directory: Path, sha256: str, record: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{sha256[:16] or 'nohash'}_{uuid.uuid4().hex[:10]}.json"
    (directory / filename).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")


def _path_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path)


def _is_hidden_or_system(path: Path) -> bool:
    for part in path.parts:
        if part.startswith("."):
            return True
    return path.name.lower() in SYSTEM_FILE_NAMES


def _file_safety_status(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in SUSPICIOUS_SUFFIXES:
        return "quarantined_suspicious", f"Suspicious executable or script suffix: {suffix}"
    if suffix and suffix not in SUPPORTED_SUFFIXES:
        return "quarantined_unsupported", f"Unsupported file suffix: {suffix}"
    if not suffix:
        return "quarantined_unsupported", "Files without an extension are not auto-extracted."
    return "accepted", ""


def _is_text_extractable(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTRACTION_SUFFIXES


def _read_text_preview(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        return "", [f"Unable to stat file before extraction: {exc}"]
    if file_size > MAX_TEXT_FILE_BYTES:
        return "", [f"Text extraction skipped because file exceeds {MAX_TEXT_FILE_BYTES} bytes."]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_CHARS]
    except OSError as exc:
        return "", [f"Unable to read text for extraction: {exc}"]
    if not text.strip():
        warnings.append("No readable text was found in the file preview.")
    return text, warnings


def _load_case_summaries(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    try:
        with db.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title FROM cases ORDER BY id")
            return [{"id": row["id"], "title": row["title"] or "Untitled Case"} for row in cursor.fetchall()]
    except Exception as exc:
        logger.warning("Unable to load cases for case folder scan: %s", exc)
        return []


def _load_case_title(case_id: int, db_path: str | Path | None = None) -> str:
    try:
        with db.get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM cases WHERE id = ?", (case_id,))
            row = cursor.fetchone()
            if row:
                return row["title"] or "Untitled Case"
    except Exception as exc:
        logger.warning("Unable to load case title for %s: %s", case_id, exc)
    return "Untitled Case"


def get_openai_api_key_from_environment() -> str | None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return api_key or None


def _mock_mode_enabled() -> bool:
    value = os.getenv("LEGAL_AGENT_INTAKE_MOCK_OPENAI", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        return [item.strip(" \t\r\n-*") for item in re.split(r"[\n;]+", value) if item.strip(" \t\r\n-*")]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return max(0.0, min(1.0, score))


def normalize_section_identifier(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    lowered = text.lower().replace(" ", "_").replace("-", "_")
    lowered = re.sub(r"[^a-z0-9_]+", "", lowered)
    for folder, label in SECTION_LABELS.items():
        if text == folder or lowered == folder or lowered == label.lower().replace(" ", "_").replace("/", ""):
            return folder
        label_key = re.sub(r"[^a-z0-9_]+", "", label.lower().replace(" ", "_"))
        if lowered == label_key:
            return folder
    return fallback or text


def _normalize_extraction(raw: dict[str, Any], current_section: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    normalized["summary"] = str(raw.get("summary") or "").strip()
    normalized["key_facts"] = _normalize_list(raw.get("key_facts"))
    normalized["parties_mentioned"] = _normalize_list(raw.get("parties_mentioned"))
    normalized["dates_and_deadlines"] = _normalize_list(raw.get("dates_and_deadlines"))
    normalized["evidence_references"] = _normalize_list(raw.get("evidence_references"))
    normalized["claims_or_defenses_mentioned"] = _normalize_list(raw.get("claims_or_defenses_mentioned"))
    normalized["jurisdiction_clues"] = _normalize_list(raw.get("jurisdiction_clues"))
    normalized["procedural_issues"] = _normalize_list(raw.get("procedural_issues"))
    normalized["legal_authorities_cited"] = _normalize_list(raw.get("legal_authorities_cited"))
    normalized["action_items"] = _normalize_list(raw.get("action_items"))
    normalized["confidence_score"] = _normalize_confidence(raw.get("confidence_score"))
    normalized["extraction_warnings"] = _normalize_list(raw.get("extraction_warnings"))
    normalized["recommended_destination_section"] = normalize_section_identifier(
        raw.get("recommended_destination_section"),
        fallback=current_section,
    )
    return normalized


def _json_from_model_response(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        stripped = stripped[start : end + 1]
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {
        "summary": text[:2000],
        "confidence_score": 0.2,
        "extraction_warnings": ["OpenAI did not return parseable JSON; raw response was preserved as the summary."],
    }


class OpenAICaseEvidenceExtractor:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.model = model
        self.provider = "openai"

    def extract(self, path: Path, text: str, section_folder: str, section_label: str) -> dict[str, Any]:
        context = (
            f"File name: {path.name}\n"
            f"Current case folder section: {section_folder} ({section_label})\n\n"
            "Document text preview:\n"
            f"{text}"
        )
        instructions = (
            "Extract structured litigation case information from the document preview. "
            "Treat the current folder as the user's primary intent signal. If the folder is "
            "05_evidence, populate evidence-oriented fields first even when facts, parties, or "
            "claims also appear. Do not invent facts, dates, authorities, parties, or deadlines. "
            "Return only valid JSON with exactly these keys: "
            + ", ".join(EXTRACTION_KEYS)
            + ". Lists must be JSON arrays of strings. confidence_score must be 0.0 to 1.0. "
            "recommended_destination_section must be one of the numbered section folder names "
            "if a different destination is strongly suggested; otherwise use the current section."
        )
        response = _chat_completion(
            api_key=self.api_key,
            context=context,
            instructions=instructions,
            system_message="You extract conservative structured legal case metadata. Return JSON only.",
            max_tokens=1400,
            action="case folder evidence extraction",
        )
        return _json_from_model_response(response)


class MockCaseEvidenceExtractor:
    provider = "mock"

    def extract(self, path: Path, text: str, section_folder: str, section_label: str) -> dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        summary = lines[0] if lines else f"Mock extraction for {path.name}"
        dates = re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b", text)
        authorities = re.findall(r"\b\d+\s+(?:U\.S\.|F\.(?:2d|3d|4th)|Cal\.(?:App\.)?\w*)\s+\d+\b", text)
        action_items = [line for line in lines if re.search(r"\b(deadline|due|serve|file by|task)\b", line, re.IGNORECASE)]
        evidence_refs = [line for line in lines if re.search(r"\b(exhibit|receipt|photo|video|email|record|contract)\b", line, re.IGNORECASE)]
        recommended = section_folder
        if action_items and section_folder != "06_action_items_due_dates":
            recommended = "06_action_items_due_dates"
        elif authorities and section_folder not in {"10_legal_research", "12_authority_validation"}:
            recommended = "12_authority_validation"
        return {
            "summary": summary[:800],
            "key_facts": lines[:5],
            "parties_mentioned": re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text)[:10],
            "dates_and_deadlines": dates,
            "evidence_references": evidence_refs,
            "claims_or_defenses_mentioned": [line for line in lines if re.search(r"\bclaim|defense|negligence|breach\b", line, re.IGNORECASE)],
            "jurisdiction_clues": [line for line in lines if re.search(r"\bCalifornia|federal|superior court|district court\b", line, re.IGNORECASE)],
            "procedural_issues": [line for line in lines if re.search(r"\bservice|filing|discovery|motion|rule\b", line, re.IGNORECASE)],
            "legal_authorities_cited": authorities,
            "action_items": action_items,
            "confidence_score": 0.75 if lines else 0.35,
            "extraction_warnings": ["Mock extraction mode; no OpenAI request was made."],
            "recommended_destination_section": recommended,
        }


def _select_extractor(extractor: Any | None, api_key: str | None) -> Any | None:
    if extractor is not None:
        return extractor
    if _mock_mode_enabled():
        return MockCaseEvidenceExtractor()
    if api_key:
        return OpenAICaseEvidenceExtractor(api_key)
    return None


def _base_file_record(
    case_id: int,
    case_title: str,
    case_dir: Path,
    path: Path,
    section_folder: str,
    sha256: str,
    file_size: int,
) -> dict[str, Any]:
    now = utc_now()
    original_path = _path_key(path)
    section_label = SECTION_LABELS.get(section_folder, section_folder)
    return {
        "record_type": "file_intake",
        "file_record_id": uuid.uuid4().hex,
        "case_id": case_id,
        "case_title": case_title,
        "case_directory": str(case_dir),
        "section_folder": section_folder,
        "section_label": section_label,
        "filename": path.name,
        "original_path": original_path,
        "original_location": str(path.parent),
        "relative_path": str(path.relative_to(case_dir)),
        "file_size": file_size,
        "sha256": sha256,
        "ingested_at": now,
        "status": "pending",
        "extraction_status": "pending_extraction",
        "duplicate": False,
        "duplicate_of": None,
        "chain_of_custody": {
            "case_id": case_id,
            "section_folder": section_folder,
            "original_path": original_path,
            "original_location": str(path.parent),
            "filename": path.name,
            "file_size": file_size,
            "hash_algorithm": "SHA256",
            "sha256": sha256,
            "captured_at": now,
            "original_preserved": True,
            "moved": False,
            "deleted": False,
        },
    }


def _pending_extraction_record(
    file_record: dict[str, Any],
    reason: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    section_folder = file_record["section_folder"]
    return {
        "record_type": "case_extraction",
        "extraction_id": uuid.uuid4().hex,
        "file_record_id": file_record["file_record_id"],
        "case_id": file_record["case_id"],
        "source_file_name": file_record["filename"],
        "source_original_path": file_record["original_path"],
        "source_section_folder": section_folder,
        "source_section_label": file_record["section_label"],
        "target_section_folder": section_folder,
        "target_section_label": file_record["section_label"],
        "status": "pending_extraction",
        "reason": reason,
        "confidence_score": 0.0,
        "review_needed": True,
        "ai_provider": "none",
        "model": "",
        "extracted_at": utc_now(),
        "recommended_destination_section": section_folder,
        "recommended_destination_label": file_record["section_label"],
        "extraction_warnings": warnings or [reason],
        "extraction": _normalize_extraction(
            {
                "summary": "",
                "confidence_score": 0.0,
                "extraction_warnings": warnings or [reason],
                "recommended_destination_section": section_folder,
            },
            section_folder,
        ),
    }


def _completed_extraction_record(
    file_record: dict[str, Any],
    extractor: Any,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    section_folder = file_record["section_folder"]
    normalized = _normalize_extraction(extraction, section_folder)
    recommended = normalized["recommended_destination_section"]
    recommended_label = SECTION_LABELS.get(recommended, recommended)
    confidence = normalized["confidence_score"]
    review_needed = bool(normalized["extraction_warnings"]) or recommended != section_folder or confidence < 0.7
    return {
        "record_type": "case_extraction",
        "extraction_id": uuid.uuid4().hex,
        "file_record_id": file_record["file_record_id"],
        "case_id": file_record["case_id"],
        "source_file_name": file_record["filename"],
        "source_original_path": file_record["original_path"],
        "source_section_folder": section_folder,
        "source_section_label": file_record["section_label"],
        "target_section_folder": section_folder,
        "target_section_label": file_record["section_label"],
        "status": "extracted",
        "confidence_score": confidence,
        "review_needed": review_needed,
        "ai_provider": getattr(extractor, "provider", "custom"),
        "model": getattr(extractor, "model", ""),
        "extracted_at": utc_now(),
        "recommended_destination_section": recommended,
        "recommended_destination_label": recommended_label,
        "extraction_warnings": normalized["extraction_warnings"],
        "extraction": normalized,
    }


def _error_record(
    case_id: int,
    section_folder: str,
    path: Path,
    message: str,
    error_type: str,
    file_record_id: str = "",
    severity: str = "error",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_type": "case_folder_event",
        "error_id": uuid.uuid4().hex,
        "case_id": case_id,
        "file_record_id": file_record_id,
        "section_folder": section_folder,
        "section_label": SECTION_LABELS.get(section_folder, section_folder),
        "original_path": _path_key(path),
        "filename": path.name,
        "severity": severity,
        "error_type": error_type,
        "message": message,
        "details": details or {},
        "created_at": utc_now(),
    }


def scan_all_case_folders(
    db_path: str | Path | None = None,
    extractor: Any | None = None,
) -> ScanResult:
    result = ScanResult()
    cases = _load_case_summaries(db_path)
    for case in cases:
        case_result = scan_case_folder(
            int(case["id"]),
            db_path=db_path,
            extractor=extractor,
            case_title=str(case["title"]),
        )
        result.merge(case_result)
    result.case_count = len(cases)
    return result


def scan_case_folder(
    case_id: int,
    db_path: str | Path | None = None,
    extractor: Any | None = None,
    case_title: str | None = None,
) -> ScanResult:
    title = case_title or _load_case_title(case_id, db_path)
    case_dir = ensure_case_folder(case_id, title, db_path=db_path)
    paths = manifest_paths(case_dir)
    result = ScanResult(case_count=1)

    existing_records = read_jsonl(paths["files"])
    seen_path_hashes = {
        (str(record.get("original_path") or ""), str(record.get("sha256") or ""))
        for record in existing_records
        if record.get("original_path") and record.get("sha256")
    }
    known_hashes: dict[str, str] = {}
    for record in existing_records:
        sha = str(record.get("sha256") or "")
        if sha and not record.get("duplicate") and sha not in known_hashes:
            known_hashes[sha] = str(record.get("file_record_id") or "")

    api_key = get_openai_api_key_from_environment()
    active_extractor = _select_extractor(extractor, api_key)
    missing_key_warning_added = False

    for section_folder in SECTION_FOLDERS:
        section_dir = case_dir / section_folder
        for path in sorted(section_dir.rglob("*")):
            if not path.is_file():
                continue
            if _is_hidden_or_system(path.relative_to(section_dir)):
                continue
            result.scanned_files += 1

            if path.is_symlink():
                record = _error_record(
                    case_id,
                    section_folder,
                    path,
                    "Symbolic links are not ingested for chain-of-custody safety.",
                    "symlink_skipped",
                    severity="warning",
                )
                append_jsonl(paths["errors"], record)
                result.quarantined_files += 1
                continue

            try:
                file_size = path.stat().st_size
                sha256 = calculate_sha256(path)
            except OSError as exc:
                append_jsonl(
                    paths["errors"],
                    _error_record(case_id, section_folder, path, str(exc), "hash_failed"),
                )
                result.failed_files += 1
                continue

            path_key = _path_key(path)
            if (path_key, sha256) in seen_path_hashes:
                result.skipped_existing += 1
                continue

            file_record = _base_file_record(case_id, title, case_dir, path, section_folder, sha256, file_size)
            result.new_files += 1
            seen_path_hashes.add((path_key, sha256))

            duplicate_of = known_hashes.get(sha256)
            if duplicate_of:
                file_record["status"] = "duplicate_skipped"
                file_record["extraction_status"] = "skipped_duplicate"
                file_record["duplicate"] = True
                file_record["duplicate_of"] = duplicate_of
                append_jsonl(paths["files"], file_record)
                result.duplicate_files += 1
                continue
            known_hashes[sha256] = file_record["file_record_id"]

            safety_status, safety_message = _file_safety_status(path)
            if safety_status != "accepted":
                file_record["status"] = safety_status
                file_record["extraction_status"] = "not_extracted"
                file_record["review_needed"] = True
                file_record["extraction_warnings"] = [safety_message]
                append_jsonl(paths["files"], file_record)
                error = _error_record(
                    case_id,
                    section_folder,
                    path,
                    safety_message,
                    safety_status,
                    file_record_id=file_record["file_record_id"],
                    severity="warning",
                )
                append_jsonl(paths["errors"], error)
                _write_sidecar(case_dir / "_quarantine", sha256, {"file": file_record, "event": error})
                result.quarantined_files += 1
                continue

            if not _is_text_extractable(path):
                reason = (
                    "The file was indexed and preserved, but local text extraction is not available "
                    "for this file type yet."
                )
                file_record["status"] = "pending_extraction"
                file_record["extraction_status"] = "pending_extraction"
                file_record["review_needed"] = True
                file_record["extraction_warnings"] = [reason]
                append_jsonl(paths["files"], file_record)
                append_jsonl(paths["extractions"], _pending_extraction_record(file_record, reason))
                result.pending_extractions += 1
                continue

            text, text_warnings = _read_text_preview(path)
            if not text.strip():
                reason = "The file was indexed, but no readable text was available for AI extraction."
                warnings = text_warnings or [reason]
                file_record["status"] = "pending_extraction"
                file_record["extraction_status"] = "pending_extraction"
                file_record["review_needed"] = True
                file_record["extraction_warnings"] = warnings
                append_jsonl(paths["files"], file_record)
                append_jsonl(paths["extractions"], _pending_extraction_record(file_record, reason, warnings))
                result.pending_extractions += 1
                continue

            if active_extractor is None:
                reason = "OPENAI_API_KEY is not configured; extraction is pending."
                file_record["status"] = "pending_extraction"
                file_record["extraction_status"] = "pending_extraction"
                file_record["review_needed"] = True
                file_record["extraction_warnings"] = [reason] + text_warnings
                append_jsonl(paths["files"], file_record)
                append_jsonl(paths["extractions"], _pending_extraction_record(file_record, reason, file_record["extraction_warnings"]))
                if not missing_key_warning_added:
                    result.warnings.append(reason)
                    missing_key_warning_added = True
                result.pending_extractions += 1
                continue

            try:
                extraction = active_extractor.extract(
                    path,
                    text,
                    section_folder,
                    SECTION_LABELS.get(section_folder, section_folder),
                )
                if text_warnings:
                    existing_warnings = _normalize_list(extraction.get("extraction_warnings"))
                    extraction["extraction_warnings"] = existing_warnings + text_warnings
                extraction_record = _completed_extraction_record(file_record, active_extractor, extraction)
                file_record["status"] = "extracted"
                file_record["extraction_status"] = "extracted"
                file_record["confidence_score"] = extraction_record["confidence_score"]
                file_record["review_needed"] = extraction_record["review_needed"]
                file_record["recommended_destination_section"] = extraction_record["recommended_destination_section"]
                file_record["recommended_destination_label"] = extraction_record["recommended_destination_label"]
                append_jsonl(paths["files"], file_record)
                append_jsonl(paths["extractions"], extraction_record)
                _write_sidecar(case_dir / "_processed", sha256, {"file": file_record, "extraction": extraction_record})
                result.extracted_files += 1
                if extraction_record["recommended_destination_section"] != section_folder:
                    recommendation = _error_record(
                        case_id,
                        section_folder,
                        path,
                        (
                            "AI suggested reviewing this file under "
                            f"{extraction_record['recommended_destination_section']} "
                            f"({extraction_record['recommended_destination_label']}). "
                            "The original file was not moved."
                        ),
                        "section_recommendation",
                        file_record_id=file_record["file_record_id"],
                        severity="info",
                        details={
                            "recommended_destination_section": extraction_record["recommended_destination_section"],
                            "recommended_destination_label": extraction_record["recommended_destination_label"],
                            "original_preserved": True,
                        },
                    )
                    append_jsonl(paths["errors"], recommendation)
            except Exception as exc:
                message = f"AI extraction failed: {exc}"
                file_record["status"] = "failed"
                file_record["extraction_status"] = "failed"
                file_record["review_needed"] = True
                file_record["extraction_warnings"] = [message]
                append_jsonl(paths["files"], file_record)
                pending = _pending_extraction_record(file_record, message, [message])
                pending["status"] = "failed"
                pending["reason"] = message
                append_jsonl(paths["extractions"], pending)
                error = _error_record(
                    case_id,
                    section_folder,
                    path,
                    message,
                    "extraction_failed",
                    file_record_id=file_record["file_record_id"],
                )
                append_jsonl(paths["errors"], error)
                _write_sidecar(case_dir / "_failed", sha256, {"file": file_record, "event": error})
                result.failed_files += 1

    return result


def list_case_file_records(case_id: int, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    title = _load_case_title(case_id, db_path)
    case_dir = ensure_case_folder(case_id, title, db_path=db_path)
    return read_jsonl(manifest_paths(case_dir)["files"])


def list_case_extractions(
    case_id: int,
    db_path: str | Path | None = None,
    section_folder: str | None = None,
) -> list[dict[str, Any]]:
    title = _load_case_title(case_id, db_path)
    case_dir = ensure_case_folder(case_id, title, db_path=db_path)
    records = read_jsonl(manifest_paths(case_dir)["extractions"])
    if section_folder:
        records = [record for record in records if record.get("target_section_folder") == section_folder]
    return records


def list_case_folder_errors(case_id: int, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    title = _load_case_title(case_id, db_path)
    case_dir = ensure_case_folder(case_id, title, db_path=db_path)
    return read_jsonl(manifest_paths(case_dir)["errors"])


def case_folder_status(case_id: int, db_path: str | Path | None = None) -> dict[str, Any]:
    title = _load_case_title(case_id, db_path)
    case_dir = ensure_case_folder(case_id, title, db_path=db_path)
    files = list_case_file_records(case_id, db_path)
    extractions = list_case_extractions(case_id, db_path)
    errors = list_case_folder_errors(case_id, db_path)
    return {
        "case_id": case_id,
        "case_title": title,
        "case_directory": str(case_dir),
        "files": len(files),
        "extractions": len(extractions),
        "errors": len(errors),
        "pending_extractions": len([record for record in extractions if record.get("status") == "pending_extraction"]),
        "failed_files": len([record for record in files if record.get("status") == "failed"]),
        "quarantined_files": len([record for record in files if str(record.get("status", "")).startswith("quarantined")]),
        "duplicate_files": len([record for record in files if record.get("duplicate")]),
    }
