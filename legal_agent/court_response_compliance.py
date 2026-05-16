from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from xml.etree import ElementTree

from .connectors.courtlistener_connector import CourtListenerConnector
from .logger import get_logger
from .openai_client import load_dotenv

logger = get_logger(__name__)

FEATURE_NAME = "Court Response Compliance Review"
SMART_REVIEW_TAB_LABEL = "Smart Document Review"
DISCLAIMER = (
    "This review is an AI-assisted compliance and risk review, not legal advice. "
    "Final filing decisions should be reviewed by a qualified attorney or appropriate legal professional."
)
NO_SAME_JURISDICTION_SUPPORT = (
    "No same-jurisdiction CourtListener support was found for this issue based on the configured search."
)
STRICT_CERTAINTY_REJECTION = (
    "The requested 100% certainty / beyond-a-reasonable-doubt threshold was not met. "
    "The system must reject any filing-ready or fully compliant certification unless every gate requirement passes."
)
NO_VULNERABILITY_PROOF_GUARANTEE = (
    "No AI system can truthfully guarantee that a legal document is vulnerability-proof or correct beyond all doubt. "
    "This feature can only mark whether the configured strict gate passed based on available same-jurisdiction support and reported confidence."
)

COURT_LEVEL_CHOICES = [
    "Municipal",
    "County",
    "Superior",
    "State trial court",
    "State appellate court",
    "State supreme court",
    "Federal district court",
    "Federal bankruptcy court",
    "Federal appellate court",
    "Other",
]

REQUEST_TYPE_CHOICES = [
    "Judge order",
    "Attorney demand",
    "Discovery request",
    "Motion opposition",
    "Motion response",
    "Notice deficiency correction",
    "Administrative agency request",
    "Court clerk correction request",
    "Other",
]

REPORT_SECTION_TITLES = [
    "Review Summary",
    "Jurisdiction Entered",
    "Court Request Context",
    "Document Type Detected",
    "Compliance Status",
    "Critical Vulnerabilities",
    "Procedural Risks",
    "Local Rule / Court Rule Issues",
    "Missing Required Content",
    "Unsupported Assertions",
    "Harmful Admissions or Risky Language",
    "Deadline / Timing Concerns",
    "Evidence and Exhibit Problems",
    "Signature / Verification / Service Problems",
    "CourtListener Same-Jurisdiction Findings",
    "Rejected Out-of-Jurisdiction Sources",
    "Recommended Corrections",
    "Confidence Score",
    "Strict Confidence Gate",
    "Generated Corrected Document",
    "Human Review Required",
]

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".rtf"}
DOCX_SUFFIXES = {".docx"}
PDF_SUFFIXES = {".pdf"}

FEDERAL_LEVELS = {
    "federal district court",
    "federal bankruptcy court",
    "federal appellate court",
}
STATE_LOCAL_LEVELS = {
    "municipal",
    "county",
    "superior",
    "state trial court",
    "state appellate court",
    "state supreme court",
    "other",
}

STATE_ALIASES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
STATE_NAMES_BY_ABBR = {abbr: name.title() for name, abbr in STATE_ALIASES.items()}

FEDERAL_CIRCUITS_BY_STATE = {
    "CA": "ninth circuit",
    "OR": "ninth circuit",
    "WA": "ninth circuit",
    "AZ": "ninth circuit",
    "NV": "ninth circuit",
    "ID": "ninth circuit",
    "MT": "ninth circuit",
    "AK": "ninth circuit",
    "HI": "ninth circuit",
    "NY": "second circuit",
    "CT": "second circuit",
    "VT": "second circuit",
    "PA": "third circuit",
    "NJ": "third circuit",
    "DE": "third circuit",
    "MD": "fourth circuit",
    "VA": "fourth circuit",
    "WV": "fourth circuit",
    "NC": "fourth circuit",
    "SC": "fourth circuit",
    "TX": "fifth circuit",
    "LA": "fifth circuit",
    "MS": "fifth circuit",
    "OH": "sixth circuit",
    "MI": "sixth circuit",
    "KY": "sixth circuit",
    "TN": "sixth circuit",
    "IL": "seventh circuit",
    "IN": "seventh circuit",
    "WI": "seventh circuit",
    "MO": "eighth circuit",
    "AR": "eighth circuit",
    "IA": "eighth circuit",
    "MN": "eighth circuit",
    "NE": "eighth circuit",
    "ND": "eighth circuit",
    "SD": "eighth circuit",
    "CO": "tenth circuit",
    "KS": "tenth circuit",
    "NM": "tenth circuit",
    "OK": "tenth circuit",
    "UT": "tenth circuit",
    "WY": "tenth circuit",
    "AL": "eleventh circuit",
    "FL": "eleventh circuit",
    "GA": "eleventh circuit",
    "DC": "district of columbia circuit",
}

REQUEST_RELEVANCE_TERMS = {
    "judge order": ["order", "court order", "show cause", "compliance"],
    "attorney demand": ["demand", "meet and confer", "letter", "response"],
    "discovery request": ["discovery", "interrogatory", "production", "admission", "response"],
    "motion opposition": ["motion", "opposition", "brief", "memorandum"],
    "motion response": ["motion", "response", "brief", "memorandum"],
    "notice deficiency correction": ["notice", "deficiency", "correction", "cure"],
    "administrative agency request": ["agency", "administrative", "request", "response"],
    "court clerk correction request": ["clerk", "correction", "deficiency", "filing"],
    "other": ["procedure", "response", "filing", "compliance"],
}


@dataclass(frozen=True)
class ReviewConfig:
    state: str
    city: str
    court_level: str
    request_type: str
    county: str = ""
    court_name: str = ""
    judge_name: str = ""
    attorney_or_requesting_party_name: str = ""
    filing_or_response_deadline: str = ""
    procedural_posture: str = ""
    user_notes: str = ""

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "ReviewConfig":
        data = {field: _clean_text(values.get(field, "")) for field in cls.__dataclass_fields__}
        return cls(**data)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def required_missing(self) -> list[str]:
        required = {
            "state": self.state,
            "city": self.city,
            "court_level": self.court_level,
            "request_type": self.request_type,
        }
        return [label for label, value in required.items() if not _clean_text(value)]

    def is_federal(self) -> bool:
        return self.court_level.strip().lower() in FEDERAL_LEVELS

    def is_state_or_local(self) -> bool:
        return self.court_level.strip().lower() in STATE_LOCAL_LEVELS


class EnvironmentCourtListenerClient:
    def __init__(self, api_key: str, cache_path: str | Path | None = None) -> None:
        self.connector = CourtListenerConnector(
            enabled=True,
            token=api_key,
            cache_path=cache_path,
        )

    def search(self, query: str, config: ReviewConfig, limit: int = 8) -> dict[str, Any]:
        response = self.connector.search_legal(query, semantic=False, bypass_cache=True)
        if not response.get("ok"):
            return response
        results = response.get("results", [])
        return {
            "ok": True,
            "status": "ok" if results else "no_results",
            "message": response.get("message", ""),
            "query": query,
            "results": results[:limit],
        }


OpenAIReviewer = Callable[[str, ReviewConfig, dict[str, Any]], dict[str, Any] | str]
DocumentGenerator = Callable[
    [str, ReviewConfig, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    dict[str, Any] | str,
]
CourtListenerReviewClient = Any


def run_court_response_compliance_review(
    document_path: str | Path | Sequence[str | Path],
    config: ReviewConfig | dict[str, Any],
    *,
    storage_root: str | Path | None = None,
    openai_reviewer: OpenAIReviewer | None = None,
    document_generator: DocumentGenerator | None = None,
    courtlistener_client: CourtListenerReviewClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    review_config = config if isinstance(config, ReviewConfig) else ReviewConfig.from_mapping(config)
    missing = review_config.required_missing()
    if missing:
        raise ValueError(
            "Review cannot begin until state, city, court level, and request type are completed. "
            f"Missing: {', '.join(missing)}."
        )

    source_paths = _normalize_document_paths(document_path)
    if not source_paths:
        raise ValueError("Choose at least one existing document before starting the compliance review.")
    for source_path in source_paths:
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"Choose an existing document before starting the compliance review: {source_path}")

    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    review_id = _build_review_id(source_paths[0], review_config, timestamp, document_count=len(source_paths))
    storage = _storage_paths(storage_root)
    _ensure_storage(storage)

    extraction = extract_review_documents(source_paths, storage["input"], review_id, timestamp, review_config)
    local_analysis = build_local_document_analysis(extraction["text"], review_config)
    ai_analysis = _run_ai_review(
        extraction["text"],
        review_config,
        extraction["metadata"],
        openai_reviewer=openai_reviewer,
    )
    merged_issues = _merge_issues(local_analysis["issues"], ai_analysis.get("issues", []))
    courtlistener = _run_courtlistener_comparison(
        review_config,
        extraction,
        ai_analysis,
        merged_issues,
        storage,
        review_id,
        courtlistener_client=courtlistener_client,
    )
    strict_gate = evaluate_strict_confidence_gate(ai_analysis, merged_issues, courtlistener, extraction)
    generated_document = generate_corrected_document(
        extraction["text"],
        review_config,
        strict_gate,
        merged_issues,
        courtlistener.get("usable_sources", []),
        extraction_metadata=extraction["metadata"],
        document_generator=document_generator,
    )
    generated_document_paths = write_generated_document(
        generated_document,
        storage["generated_documents"],
        review_id,
    )
    generated_document["paths"] = generated_document_paths
    report = assemble_review_report(
        review_id,
        review_config,
        extraction,
        local_analysis,
        ai_analysis,
        merged_issues,
        courtlistener,
        strict_gate,
        generated_document,
        timestamp,
    )
    report_paths = write_review_report(report, storage["reports"], review_id)
    _write_manifest(storage["manifest"], review_id, report, extraction, report_paths)
    return {
        "ok": True,
        "review_id": review_id,
        "report": report,
        "report_paths": report_paths,
        "generated_document": generated_document,
        "generated_document_paths": generated_document_paths,
        "storage_root": str(storage["root"]),
    }


def extract_document_text(
    source_path: str | Path,
    input_dir: str | Path,
    review_id: str,
    timestamp: datetime,
    config: ReviewConfig,
) -> dict[str, Any]:
    path = Path(source_path).expanduser()
    file_hash = _sha256_file(path)
    safe_name = _safe_filename(path.name)
    preserved_path = Path(input_dir) / f"{review_id}_{safe_name}"
    shutil.copy2(path, preserved_path)

    suffix = path.suffix.lower()
    text = ""
    status = "extracted"
    method = "plain_text"
    warnings: list[str] = []
    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix in DOCX_SUFFIXES:
        text, status, method, warnings = _extract_docx_text(path)
    elif suffix in PDF_SUFFIXES:
        text, status, method, warnings = _extract_pdf_text(path)
    else:
        text, status, method, warnings = _best_effort_text(path)

    metadata = {
        "filename": path.name,
        "original_path": str(path),
        "preserved_document_path": str(preserved_path),
        "file_hash_sha256": file_hash,
        "timestamp": timestamp.isoformat(),
        "extraction_status": status,
        "extraction_method": method,
        "warnings": warnings,
        "review_configuration": config.to_dict(),
        "text_character_count": len(text),
    }
    return {
        "text": text,
        "metadata": metadata,
    }


def extract_review_documents(
    source_paths: Sequence[str | Path],
    input_dir: str | Path,
    review_id: str,
    timestamp: datetime,
    config: ReviewConfig,
) -> dict[str, Any]:
    extracted_documents: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for index, source_path in enumerate(source_paths, start=1):
        document_review_id = review_id if len(source_paths) == 1 else f"{review_id}_{index:02d}"
        extracted = extract_document_text(source_path, input_dir, document_review_id, timestamp, config)
        extracted_documents.append(extracted)
        label = extracted["metadata"].get("filename", f"document {index}")
        text_parts.append(f"\n\n===== DOCUMENT {index}: {label} =====\n\n{extracted['text']}")

    if len(extracted_documents) == 1:
        return extracted_documents[0]

    document_metadata = [document["metadata"] for document in extracted_documents]
    combined_hash = hashlib.sha256(
        "\n".join(metadata.get("file_hash_sha256", "") for metadata in document_metadata).encode("utf-8")
    ).hexdigest()
    combined_metadata = {
        "filename": f"{len(extracted_documents)} submitted documents",
        "original_path": "; ".join(metadata.get("original_path", "") for metadata in document_metadata),
        "preserved_document_path": document_metadata[0].get("preserved_document_path", ""),
        "preserved_document_paths": [metadata.get("preserved_document_path", "") for metadata in document_metadata],
        "file_hash_sha256": combined_hash,
        "timestamp": timestamp.isoformat(),
        "extraction_status": "extracted",
        "extraction_method": "combined",
        "warnings": [warning for metadata in document_metadata for warning in metadata.get("warnings", [])],
        "review_configuration": config.to_dict(),
        "text_character_count": sum(len(document["text"]) for document in extracted_documents),
        "documents": document_metadata,
    }
    return {
        "text": "\n".join(text_parts).strip(),
        "metadata": combined_metadata,
    }


def build_local_document_analysis(document_text: str, config: ReviewConfig) -> dict[str, Any]:
    text = document_text or ""
    lower = text.lower()
    document_type = _detect_document_type(text, config)
    purpose = _detect_response_purpose(text, config)
    issues: list[dict[str, Any]] = []

    if len(text.strip()) < 300:
        issues.append(
            _issue(
                "Missing Required Content",
                "Document text appears very short or could not be fully extracted",
                "Entire document",
                "A response document with little extractable text may omit required argument, factual support, attachments, or service language.",
                "The court may reject the filing, require correction, or treat the response as incomplete.",
                "Confirm the source file is text-searchable and contains the full response before filing.",
                "High",
                0.82,
                True,
            )
        )

    if not _has_caption(text, config):
        issues.append(
            _issue(
                "Local Rule / Court Rule Issues",
                "Caption or court identification may be missing",
                "Document heading",
                "Most court response filings need a caption identifying the court, parties, and case context.",
                "The clerk may reject the filing or the court may require a corrected document.",
                "Add the exact court caption, case number if applicable, parties, and response title required by the selected court.",
                "High",
                0.78,
                True,
            )
        )

    if not _mentions_request_context(text, config):
        issues.append(
            _issue(
                "Procedural Risks",
                "Response may not directly answer the selected request type",
                "Purpose / introduction",
                "A response should make clear whether it answers a judge order, attorney demand, discovery request, motion, deficiency notice, or other configured request.",
                "The court or requesting party may treat the response as nonresponsive or waived in part.",
                "Add a concise opening paragraph identifying the request being answered and each requested item being addressed.",
                "High",
                0.8,
                True,
            )
        )

    if config.filing_or_response_deadline and config.filing_or_response_deadline.lower() not in lower:
        issues.append(
            _issue(
                "Deadline / Timing Concerns",
                "Configured deadline is not referenced in the document",
                "Deadline discussion",
                "The user entered a filing or response deadline, but the response does not appear to address timeliness.",
                "A missed or unclear deadline can create default, sanctions, waiver, or rejection risk.",
                "Confirm the deadline calculation and add any needed timeliness statement or service date support.",
                "High",
                0.74,
                True,
            )
        )

    if _has_unsupported_assertions(text):
        issues.append(
            _issue(
                "Unsupported Assertions",
                "Broad factual or legal assertions may lack record support",
                "Argument / factual assertions",
                "Statements using absolute or conclusory phrasing should be tied to evidence, declarations, exhibits, verified facts, or valid same-jurisdiction authority.",
                "Unsupported assertions may be disregarded and may weaken credibility or create sanctions exposure.",
                "Tie each material assertion to an exhibit, declaration, verified record citation, or validated same-jurisdiction authority.",
                "Medium",
                0.7,
                True,
            )
        )

    risky_language_location = _risky_language_location(text)
    if risky_language_location:
        issues.append(
            _issue(
                "Harmful Admissions or Risky Language",
                "Potentially harmful admission or concession language detected",
                risky_language_location,
                "Admission-style language can create financial, procedural, evidentiary, default, waiver, or sanctions risk if not intentional and supported.",
                "The statement may be used against the filer or treated as a waiver or concession.",
                "Have counsel review the language and revise to preserve objections, avoid unnecessary admissions, and state only verified facts.",
                "Critical",
                0.76,
                True,
            )
        )

    if _mentions_exhibits_without_attachments(text):
        issues.append(
            _issue(
                "Evidence and Exhibit Problems",
                "Referenced exhibits may not be attached or identified",
                "Exhibit references",
                "The document references exhibits but does not clearly list, attach, or authenticate them.",
                "The court may disregard unsupported evidence or require a corrected filing.",
                "Add an exhibit list, attach each referenced exhibit, and include a declaration or authentication language where required.",
                "High",
                0.72,
                True,
            )
        )

    if not _has_signature(text):
        issues.append(
            _issue(
                "Signature / Verification / Service Problems",
                "Signature block appears missing",
                "End of document",
                "Court responses generally require a signature by the self-represented party or attorney, and some responses require verification.",
                "The filing may be rejected, stricken, or treated as procedurally defective.",
                "Add the required signature block, date, typed name, contact information, and verification if required by the request type.",
                "Critical",
                0.86,
                True,
            )
        )

    if not _has_proof_of_service(text):
        issues.append(
            _issue(
                "Signature / Verification / Service Problems",
                "Proof of service appears missing",
                "Service section / end of document",
                "Responses usually must be served on the other side or requesting party unless the court's e-filing system and rules provide otherwise.",
                "A missing proof of service can cause rejection, delay, sanctions exposure, or ineffective service.",
                "Add a proof or certificate of service that matches the selected court's service rules and the parties served.",
                "High",
                0.82,
                True,
            )
        )

    inconsistent_names = _detect_name_context_mismatch(text, config)
    if inconsistent_names:
        issues.append(
            _issue(
                "Critical Vulnerabilities",
                "Configured judge, court, attorney, or party context may be missing from the response",
                inconsistent_names,
                "The response context should match the judge, court, attorney, or requesting party information entered by the user.",
                "A mismatch can make the filing look nonresponsive or create case-identification risk.",
                "Confirm all names, case references, court information, and requesting-party details before submission.",
                "Medium",
                0.68,
                True,
            )
        )

    return {
        "document_type": document_type,
        "court_response_purpose": purpose,
        "possible_procedural_obligations": _procedural_obligations(config),
        "issues": issues,
    }


def validate_courtlistener_result(
    result: dict[str, Any],
    config: ReviewConfig,
    *,
    request_type: str | None = None,
) -> dict[str, Any]:
    title = _clean_text(result.get("title", "Untitled CourtListener result"))
    combined = _combined_result_text(result)
    scope = _result_scope(result)
    state_check = _matches_selected_state_or_controlling_federal_scope(combined, config, scope)
    if not state_check["ok"]:
        return _validation(False, title, state_check["reason"])

    if config.is_federal() and scope["system"] != "federal":
        return _validation(
            False,
            title,
            "State or local authority cannot support a federal court review unless the selected court level is state/local.",
        )
    if config.is_state_or_local() and scope["system"] == "federal":
        return _validation(
            False,
            title,
            "Federal authority cannot support a state or local court review unless a federal court level is selected.",
        )

    level_check = _matches_controlling_court_level(scope, combined, config)
    if not level_check["ok"]:
        return _validation(False, title, level_check["reason"])

    venue_check = _matches_trial_venue(scope, combined, config)
    if not venue_check["ok"]:
        return _validation(False, title, venue_check["reason"])

    relevance_check = _matches_request_relevance(combined, request_type or config.request_type)
    if not relevance_check["ok"]:
        return _validation(False, title, relevance_check["reason"])

    return _validation(True, title, "Matches the selected jurisdiction, court hierarchy, venue scope, and request type.")


def write_review_report(report: dict[str, Any], reports_dir: str | Path, review_id: str) -> dict[str, str]:
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{review_id}.json"
    markdown_path = directory / f"{review_id}.md"
    pdf_path = directory / f"{review_id}.pdf"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(report_to_markdown(report), encoding="utf-8")
    _write_simple_pdf(pdf_path, report_to_plain_text(report))
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "pdf": str(pdf_path),
    }


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {FEATURE_NAME}", ""]
    lines.append(DISCLAIMER)
    lines.append("")
    for section in REPORT_SECTION_TITLES:
        lines.append(f"## {section}")
        lines.extend(_markdown_lines_for_value(report.get(section, "")))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def report_to_plain_text(report: dict[str, Any]) -> str:
    return re.sub(r"[#*`]", "", report_to_markdown(report))


def evaluate_strict_confidence_gate(
    ai_analysis: dict[str, Any],
    issues: list[dict[str, Any]],
    courtlistener: dict[str, Any],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    usable_sources = courtlistener.get("usable_sources", [])
    reported_certainty = _bounded_float(ai_analysis.get("confidence_score"), 0.0)
    rejection_reasons: list[str] = []

    if reported_certainty < 1.0:
        rejection_reasons.append("OpenAI analysis did not report 100% certainty.")
    if not usable_sources:
        rejection_reasons.append("No validated same-jurisdiction CourtListener reference is available.")

    unresolved_issues = [issue for issue in issues if issue.get("severity") in {"Critical", "High", "Medium", "Low", "Informational"}]
    if unresolved_issues:
        rejection_reasons.append("The review still contains unresolved findings, so a vulnerability-proof certification is not available.")

    issue_confidence_below_full = [
        issue.get("issue_title", "issue")
        for issue in issues
        if _bounded_float(issue.get("confidence_score"), 0.0) < 1.0
    ]
    if issue_confidence_below_full:
        rejection_reasons.append("At least one finding has less than 100% confidence.")

    metadata = extraction.get("metadata", {})
    if metadata.get("extraction_status") not in {"extracted", "best_effort_text"}:
        rejection_reasons.append("The document text was not fully extracted with a reliable method.")
    if metadata.get("warnings"):
        rejection_reasons.append("Extraction warnings were present.")

    accepted = not rejection_reasons
    return {
        "accepted": accepted,
        "required_certainty": 1.0,
        "reported_certainty": reported_certainty,
        "usable_reference_count": len(usable_sources),
        "references": usable_sources,
        "rejection_reasons": rejection_reasons,
        "message": (
            "The configured strict gate passed. This does not remove the need for human legal review."
            if accepted
            else STRICT_CERTAINTY_REJECTION
        ),
        "non_guarantee_notice": NO_VULNERABILITY_PROOF_GUARANTEE,
        "filing_ready_output_allowed": accepted,
    }


def generate_corrected_document(
    document_text: str,
    config: ReviewConfig,
    strict_gate: dict[str, Any],
    issues: list[dict[str, Any]],
    usable_sources: list[dict[str, Any]],
    extraction_metadata: dict[str, Any] | None = None,
    *,
    document_generator: DocumentGenerator | None = None,
) -> dict[str, Any]:
    if document_generator is not None:
        try:
            return _with_combined_source_info(
                _normalize_generated_document(
                    document_generator(document_text, config, strict_gate, issues, usable_sources),
                    strict_gate,
                    usable_sources,
                ),
                extraction_metadata,
            )
        except Exception as exc:
            logger.exception("Injected document generator failed")
            return _with_combined_source_info(
                _fallback_generated_document(document_text, config, strict_gate, issues, usable_sources, extraction_metadata, error=str(exc)),
                extraction_metadata,
            )

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _with_combined_source_info(
            _fallback_generated_document(document_text, config, strict_gate, issues, usable_sources, extraction_metadata),
            extraction_metadata,
        )

    try:
        from .openai_client import _chat_completion

        context = json.dumps(
            {
                "jurisdiction": config.to_dict(),
                "strict_gate": strict_gate,
                "validated_same_jurisdiction_sources": usable_sources,
                "issues_to_correct": issues,
                "source_documents": _combined_source_info(extraction_metadata),
                "original_document_text": document_text[:45000],
            },
            indent=2,
            default=str,
        )
        generated = _chat_completion(
            api_key=api_key,
            context=context,
            instructions=_openai_document_generation_instructions(),
            system_message=(
                "Generate conservative legal document drafts only from the user context and validated same-jurisdiction references. "
                "Do not claim certainty, filing readiness, or legal advice."
            ),
            max_tokens=3600,
            action="court response corrected document generation",
        )
        return _with_combined_source_info(
            _normalize_generated_document(generated, strict_gate, usable_sources),
            extraction_metadata,
        )
    except Exception as exc:
        logger.exception("OpenAI corrected document generation failed")
        return _with_combined_source_info(
            _fallback_generated_document(document_text, config, strict_gate, issues, usable_sources, extraction_metadata, error=str(exc)),
            extraction_metadata,
        )


def write_generated_document(
    generated_document: dict[str, Any],
    generated_dir: str | Path,
    review_id: str,
) -> dict[str, str]:
    directory = Path(generated_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{review_id}_generated_document.json"
    markdown_path = directory / f"{review_id}_generated_document.md"
    pdf_path = directory / f"{review_id}_generated_document.pdf"
    json_path.write_text(json.dumps(generated_document, indent=2, sort_keys=True, default=str), encoding="utf-8")
    markdown_path.write_text(generated_document.get("content_markdown", ""), encoding="utf-8")
    _write_simple_pdf(pdf_path, generated_document.get("content_markdown", ""))
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "pdf": str(pdf_path),
    }


def assemble_review_report(
    review_id: str,
    config: ReviewConfig,
    extraction: dict[str, Any],
    local_analysis: dict[str, Any],
    ai_analysis: dict[str, Any],
    issues: list[dict[str, Any]],
    courtlistener: dict[str, Any],
    strict_gate: dict[str, Any],
    generated_document: dict[str, Any],
    timestamp: datetime,
) -> dict[str, Any]:
    usable_sources = courtlistener.get("usable_sources", [])
    rejected_sources = courtlistener.get("rejected_sources", [])
    supported_issues = _attach_same_jurisdiction_support(issues, usable_sources)
    critical = [issue for issue in supported_issues if issue["severity"] == "Critical"]
    high = [issue for issue in supported_issues if issue["severity"] == "High"]
    status = "Not ready for filing" if critical or high else "Potentially ready after human review"
    if courtlistener.get("status") in {"unavailable", "credentials_missing", "error"}:
        comparison_summary: Any = {
            "status": courtlistener.get("status"),
            "message": courtlistener.get("message"),
            "usable_sources": [],
        }
    elif usable_sources:
        comparison_summary = usable_sources
    else:
        comparison_summary = {
            "message": NO_SAME_JURISDICTION_SUPPORT,
            "usable_sources": [],
        }

    report = {
        "review_id": review_id,
        "generated_at": timestamp.isoformat(),
        "feature": FEATURE_NAME,
        "disclaimer": DISCLAIMER,
        "storage": {
            "preserved_document_path": extraction["metadata"].get("preserved_document_path"),
            "file_hash_sha256": extraction["metadata"].get("file_hash_sha256"),
        },
        "Review Summary": {
            "status": status,
            "issue_count": len(supported_issues),
            "critical_count": len(critical),
            "high_count": len(high),
            "courtlistener_status": courtlistener.get("status"),
            "ai_analysis_mode": ai_analysis.get("mode"),
            "strict_gate_accepted": strict_gate.get("accepted", False),
            "generated_document_status": generated_document.get("status"),
            "disclaimer": DISCLAIMER,
        },
        "Jurisdiction Entered": {
            "State": config.state,
            "City": config.city,
            "County": config.county or "Not provided",
            "Court level": config.court_level,
            "Court name": config.court_name or "Not provided",
        },
        "Court Request Context": {
            "Judge name": config.judge_name or "Not provided",
            "Attorney/requesting party name": config.attorney_or_requesting_party_name or "Not provided",
            "Request type": config.request_type,
            "Filing or response deadline": config.filing_or_response_deadline or "Not provided",
            "Procedural posture": config.procedural_posture or "Not provided",
            "User notes/context": config.user_notes or "Not provided",
        },
        "Document Type Detected": ai_analysis.get("document_type_detected") or local_analysis.get("document_type"),
        "Compliance Status": {
            "status": status,
            "reason": "Critical or high risks were found." if critical or high else "No critical or high risks were detected by this review.",
            "human_review_required": True,
        },
        "Critical Vulnerabilities": _issues_for_section(supported_issues, "Critical Vulnerabilities"),
        "Procedural Risks": _issues_for_section(supported_issues, "Procedural Risks"),
        "Local Rule / Court Rule Issues": _issues_for_section(supported_issues, "Local Rule / Court Rule Issues"),
        "Missing Required Content": _issues_for_section(supported_issues, "Missing Required Content"),
        "Unsupported Assertions": _issues_for_section(supported_issues, "Unsupported Assertions"),
        "Harmful Admissions or Risky Language": _issues_for_section(supported_issues, "Harmful Admissions or Risky Language"),
        "Deadline / Timing Concerns": _issues_for_section(supported_issues, "Deadline / Timing Concerns"),
        "Evidence and Exhibit Problems": _issues_for_section(supported_issues, "Evidence and Exhibit Problems"),
        "Signature / Verification / Service Problems": _issues_for_section(supported_issues, "Signature / Verification / Service Problems"),
        "CourtListener Same-Jurisdiction Findings": comparison_summary,
        "Rejected Out-of-Jurisdiction Sources": rejected_sources,
        "Recommended Corrections": _recommended_corrections(supported_issues),
        "Confidence Score": {
            "overall": _overall_confidence(supported_issues, ai_analysis, courtlistener),
            "basis": "Derived from extraction quality, AI/local issue confidence, and same-jurisdiction CourtListener validation status.",
        },
        "Strict Confidence Gate": strict_gate,
        "Generated Corrected Document": {
            "status": generated_document.get("status"),
            "certification_status": generated_document.get("certification_status"),
            "paths": generated_document.get("paths", {}),
            "summary": generated_document.get("summary"),
            "warning": generated_document.get("warning"),
            "references_used": generated_document.get("references_used", []),
            "combines_multiple_sources": generated_document.get("combines_multiple_sources", False),
            "combined_source_document_count": generated_document.get("combined_source_document_count", 1),
            "combined_source_filenames": generated_document.get("combined_source_filenames", []),
        },
        "Human Review Required": {
            "required": True,
            "attorney_review_strongly_recommended": bool(critical or high),
            "message": DISCLAIMER,
        },
        "Extraction Metadata": extraction["metadata"],
        "All Issues": supported_issues,
        "AI Analysis Raw": ai_analysis.get("raw_response", ""),
        "CourtListener Query Records": courtlistener.get("query_records", []),
    }
    for title in REPORT_SECTION_TITLES:
        report.setdefault(title, [] if "Issues" in title or "Problems" in title else "")
    return report


def _run_ai_review(
    document_text: str,
    config: ReviewConfig,
    extraction_metadata: dict[str, Any],
    *,
    openai_reviewer: OpenAIReviewer | None,
) -> dict[str, Any]:
    if openai_reviewer is not None:
        try:
            return _normalize_ai_analysis(openai_reviewer(document_text, config, extraction_metadata))
        except Exception as exc:
            logger.exception("Mocked or injected OpenAI reviewer failed")
            return {
                "mode": "openai_reviewer_error",
                "issues": [],
                "raw_response": str(exc),
                "document_type_detected": "",
            }

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            "mode": "local_fallback_no_openai_key",
            "issues": [],
            "raw_response": "OPENAI_API_KEY is not configured; used local heuristic issue spotting only.",
            "document_type_detected": "",
        }

    try:
        from .openai_client import _chat_completion

        context = json.dumps(
            {
                "jurisdiction": config.to_dict(),
                "extraction_metadata": extraction_metadata,
                "document_text": document_text[:45000],
            },
            indent=2,
        )
        response = _chat_completion(
            api_key=api_key,
            context=context,
            instructions=_openai_review_instructions(),
            system_message=(
                "You are the primary legal response compliance reviewer. "
                "Do not create or cite authority outside the user-entered jurisdiction."
            ),
            max_tokens=2600,
            action="court response compliance review",
        )
        return _normalize_ai_analysis(response)
    except Exception as exc:
        logger.exception("OpenAI compliance review failed")
        return {
            "mode": "openai_error_local_fallback",
            "issues": [],
            "raw_response": f"OpenAI review failed: {str(exc)[:300]}",
            "document_type_detected": "",
        }


def _run_courtlistener_comparison(
    config: ReviewConfig,
    extraction: dict[str, Any],
    ai_analysis: dict[str, Any],
    issues: list[dict[str, Any]],
    storage: dict[str, Path],
    review_id: str,
    *,
    courtlistener_client: CourtListenerReviewClient | None,
) -> dict[str, Any]:
    query = _build_courtlistener_query(config, ai_analysis, issues)
    api_key = os.getenv("COURTLISTENER_API_KEY", "").strip()
    query_records: list[dict[str, Any]] = []
    if courtlistener_client is None:
        if not api_key:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "review_id": review_id,
                "query": query,
                "status": "unavailable",
                "message": "COURTLISTENER_API_KEY is missing; CourtListener comparison was not run.",
            }
            _append_jsonl(storage["queries"], record)
            return {
                "status": "unavailable",
                "message": "CourtListener comparison unavailable because COURTLISTENER_API_KEY is missing.",
                "query": query,
                "usable_sources": [],
                "rejected_sources": [],
                "query_records": [record],
            }
        courtlistener_client = EnvironmentCourtListenerClient(api_key, cache_path=storage["logs"] / "courtlistener_cache.json")

    try:
        response = courtlistener_client.search(query, config, limit=8)
    except Exception as exc:
        logger.exception("CourtListener same-jurisdiction comparison failed")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "review_id": review_id,
            "query": query,
            "status": "error",
            "message": str(exc)[:300],
        }
        _append_jsonl(storage["queries"], record)
        return {
            "status": "error",
            "message": f"CourtListener comparison failed: {str(exc)[:200]}",
            "query": query,
            "usable_sources": [],
            "rejected_sources": [],
            "query_records": [record],
        }

    usable_sources: list[dict[str, Any]] = []
    rejected_sources: list[dict[str, Any]] = []
    for result in response.get("results", []):
        validation = validate_courtlistener_result(result, config)
        source_record = _source_record(review_id, query, result, validation)
        query_records.append(source_record)
        _append_jsonl(storage["queries"], source_record)
        if validation["usable"]:
            usable_sources.append(source_record)
        else:
            rejected_sources.append(source_record)
            _append_jsonl(storage["rejected_log"], source_record)

    if rejected_sources:
        rejected_review_path = storage["rejected_sources"] / f"{review_id}.json"
        rejected_review_path.write_text(json.dumps(rejected_sources, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "status": "ok" if response.get("ok") else response.get("status", "error"),
        "message": response.get("message", ""),
        "query": query,
        "usable_sources": usable_sources,
        "rejected_sources": rejected_sources,
        "query_records": query_records,
    }


def _openai_review_instructions() -> str:
    return f"""
Return only valid JSON. Do not use markdown fences.

Purpose:
Review the submitted legal response before filing or submission.

Mandatory jurisdiction rule:
- User-entered jurisdiction data is the controlling source of truth.
- Never cite, rely on, recommend, or analogize to another city, county, state, court level, or unrelated jurisdiction.
- If same-jurisdiction support is unavailable, use exactly: "{NO_SAME_JURISDICTION_SUPPORT}"
- Do not invent citations, rules, cases, source URLs, local rules, judge preferences, or filing requirements.

Primary review tasks:
- Identify document type and court-response purpose.
- Identify possible procedural obligations, formatting/local-rule issues, missing sections, risky admissions, unsupported assertions, inconsistent dates/names/parties/deadlines/case references, missing exhibits/declarations/verifications/signatures/proofs of service, and whether the document answers the configured request.

Return this JSON shape:
{{
  "document_type_detected": "string",
  "court_response_purpose": "string",
  "issues": [
    {{
      "section": "one of the required report section names",
      "severity": "Critical|High|Medium|Low|Informational",
      "issue_title": "string",
      "location_in_document": "string",
      "why_it_matters": "string",
      "possible_consequence": "string",
      "recommended_correction": "string",
      "confidence_score": 0.0,
      "attorney_review_strongly_recommended": true
    }}
  ],
  "confidence_score": 0.0
}}
"""


def _openai_document_generation_instructions() -> str:
    return f"""
Return only valid JSON. Do not use markdown fences.

Task:
Create a conservative corrected legal response draft from the user's document and review configuration.

Mandatory limits:
- Use the user-entered jurisdiction as the controlling source of truth.
- Use only validated same-jurisdiction CourtListener references supplied in the context.
- Do not cite or rely on rejected or out-of-jurisdiction sources.
- Do not claim the document is legally sufficient, vulnerability-proof, guaranteed compliant, or beyond reasonable doubt.
- If the strict gate did not pass, label the draft as NOT CERTIFIED FOR FILING.
- Include this disclaimer: "{DISCLAIMER}"

Drafting expectations:
- If multiple source documents are provided, combine them into one integrated corrected response draft. Do not create separate drafts per file.
- Include a court-style caption placeholder using the configured court, county, city, judge, parties, and case number placeholders where missing.
- Identify the request being answered.
- Organize the response into numbered sections.
- Preserve objections and avoid harmful admissions where appropriate.
- Include sections for evidence/exhibits, declarations/verification where applicable, signature, and proof/certificate of service placeholders.
- Identify same-jurisdiction references used, if any, without adding new authorities.

Return this JSON shape:
{{
  "summary": "string",
  "content_markdown": "full corrected draft in markdown",
  "references_used": [
    {{"case_title": "string", "court": "string", "url_or_source_id": "string", "reason": "string"}}
  ]
}}
"""


def _normalize_generated_document(
    value: dict[str, Any] | str,
    strict_gate: dict[str, Any],
    usable_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_response = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    payload = value if isinstance(value, dict) else _extract_json_object(value)
    content = _clean_generated_markdown(payload.get("content_markdown") or payload.get("draft") or raw_response)
    return {
        "status": "filing_ready_output_allowed" if strict_gate.get("accepted") else "draft_created_but_certification_rejected",
        "certification_status": "accepted" if strict_gate.get("accepted") else "rejected",
        "summary": _clean_text(payload.get("summary") or "Corrected response draft generated for attorney review."),
        "content_markdown": _prepend_generated_document_gate_notice(content, strict_gate),
        "references_used": _normalize_reference_list(payload.get("references_used"), usable_sources),
        "warning": "" if strict_gate.get("accepted") else STRICT_CERTAINTY_REJECTION,
        "non_guarantee_notice": NO_VULNERABILITY_PROOF_GUARANTEE,
        "raw_response": raw_response,
    }


def _fallback_generated_document(
    document_text: str,
    config: ReviewConfig,
    strict_gate: dict[str, Any],
    issues: list[dict[str, Any]],
    usable_sources: list[dict[str, Any]],
    extraction_metadata: dict[str, Any] | None = None,
    *,
    error: str = "",
) -> dict[str, Any]:
    content = _fallback_corrected_document_markdown(document_text, config, issues, usable_sources, strict_gate, extraction_metadata)
    if error:
        content += f"\n\n## Generation Error\n\nOpenAI document generation failed and the local fallback was used: {error[:300]}\n"
    return {
        "status": "filing_ready_output_allowed" if strict_gate.get("accepted") else "draft_created_but_certification_rejected",
        "certification_status": "accepted" if strict_gate.get("accepted") else "rejected",
        "summary": "Local corrected response draft generated from the review configuration and detected issues.",
        "content_markdown": content,
        "references_used": _normalize_reference_list([], usable_sources),
        "warning": "" if strict_gate.get("accepted") else STRICT_CERTAINTY_REJECTION,
        "non_guarantee_notice": NO_VULNERABILITY_PROOF_GUARANTEE,
        "raw_response": "local_fallback",
    }


def _fallback_corrected_document_markdown(
    document_text: str,
    config: ReviewConfig,
    issues: list[dict[str, Any]],
    usable_sources: list[dict[str, Any]],
    strict_gate: dict[str, Any],
    extraction_metadata: dict[str, Any] | None = None,
) -> str:
    status_line = "STRICT GATE ACCEPTED" if strict_gate.get("accepted") else "NOT CERTIFIED FOR FILING"
    source_info = _combined_source_info(extraction_metadata)
    source_lines = [
        f"- {filename}"
        for filename in source_info["combined_source_filenames"]
    ] or ["- No source filename was recorded."]
    references = usable_sources or []
    reference_lines = [
        f"- {source.get('case_title', 'CourtListener result')} ({source.get('court', 'court unknown')}) - {source.get('url_or_source_id', 'no URL/source ID')}"
        for source in references
    ] or [f"- {NO_SAME_JURISDICTION_SUPPORT}"]
    correction_lines = [
        f"- {issue.get('issue_title')}: {issue.get('recommended_correction')}"
        for issue in issues
    ] or ["- No specific corrections were detected by the review layer; confirm local formatting and service requirements."]
    original_excerpt = document_text.strip()[:4000] or "[No extractable original text was available.]"
    return f"""# Proposed Corrected Court Response Draft

**Status:** {status_line}

{DISCLAIMER}

{NO_VULNERABILITY_PROOF_GUARANTEE}

## Court Caption

{config.court_name or '[COURT NAME]'}

{config.city}, {config.county or '[COUNTY]'}, {config.state}

Judge: {config.judge_name or '[JUDGE NAME IF REQUIRED]'}

Case No.: [CASE NUMBER]

[PARTY NAME], [PARTY ROLE],

v.

[OPPOSING PARTY NAME], [PARTY ROLE].

## Title

Response to {config.request_type}

## Preliminary Statement

This response is submitted in connection with the {config.request_type.lower()} in the above-captioned matter. The response is limited to the court, venue, procedural posture, and request context identified by the filer.

## Source Documents Combined

This generated draft combines {source_info["combined_source_document_count"]} uploaded source document(s) into one proposed response draft.

{chr(10).join(source_lines)}

## Jurisdiction and Venue Confirmation

The filer should confirm that this document is intended for {config.court_name or 'the selected court'} in {config.city}, {config.county or '[county if applicable]'}, {config.state}, at the {config.court_level} level. No out-of-jurisdiction authority should be cited or relied upon.

## Response

1. The responding party answers the request as follows: [INSERT DIRECT ANSWER TO EACH ORDER, DEMAND, REQUEST, MOTION POINT, DEFICIENCY, OR CLERK CORRECTION.]
2. The responding party preserves all applicable objections, defenses, privileges, and procedural protections unless expressly and knowingly waived.
3. Any factual statement should be supported by an attached exhibit, declaration, verification, or record citation.
4. Any legal statement should be supported only by controlling local rules, court orders, statutes, or validated same-jurisdiction authority.

## Corrections Engineered Into This Draft

{chr(10).join(correction_lines)}

## Same-Jurisdiction References Available

{chr(10).join(reference_lines)}

## Exhibits and Declarations

Attach and label each referenced exhibit. Add a declaration or verification if the selected request type or court rule requires sworn factual support.

## Signature

Dated: [DATE]

Respectfully submitted,

[SIGNATURE]

[PRINTED NAME]

[ADDRESS / EMAIL / TELEPHONE IF REQUIRED]

## Proof or Certificate of Service

I certify that on [DATE], I served this response on all required parties by [METHOD OF SERVICE] at the addresses required by the applicable court rules and orders.

[SIGNATURE OF SERVER OR FILING PARTY IF PERMITTED]

## Original Text Considered

```text
{original_excerpt}
```
"""


def _prepend_generated_document_gate_notice(content: str, strict_gate: dict[str, Any]) -> str:
    status_line = "STRICT GATE ACCEPTED" if strict_gate.get("accepted") else "NOT CERTIFIED FOR FILING"
    notice = f"# Proposed Corrected Court Response Draft\n\n**Status:** {status_line}\n\n{DISCLAIMER}\n\n{NO_VULNERABILITY_PROOF_GUARANTEE}\n"
    if content.lstrip().startswith("# Proposed Corrected Court Response Draft"):
        return content
    return f"{notice}\n{content.strip()}\n"


def _clean_generated_markdown(value: Any) -> str:
    text = str(value or "").strip()
    return text or "# Proposed Corrected Court Response Draft\n\n[No draft content was generated.]\n"


def _normalize_reference_list(value: Any, usable_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_map = {
        (source.get("case_title"), source.get("url_or_source_id")): source
        for source in usable_sources
    }
    references: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                key = (item.get("case_title"), item.get("url_or_source_id"))
                if key in source_map:
                    references.append(source_map[key])
    if references:
        return references
    return usable_sources


def _with_combined_source_info(
    generated_document: dict[str, Any],
    extraction_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    source_info = _combined_source_info(extraction_metadata)
    enriched = dict(generated_document)
    enriched.update(source_info)
    if source_info["combines_multiple_sources"] and "Source Documents Combined" not in enriched.get("content_markdown", ""):
        source_lines = "\n".join(f"- {filename}" for filename in source_info["combined_source_filenames"])
        enriched["content_markdown"] = (
            enriched.get("content_markdown", "").rstrip()
            + "\n\n## Source Documents Combined\n\n"
            + f"This generated draft combines {source_info['combined_source_document_count']} uploaded source documents into one proposed response draft.\n\n"
            + source_lines
            + "\n"
        )
    return enriched


def _combined_source_info(extraction_metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = extraction_metadata if isinstance(extraction_metadata, dict) else {}
    documents = metadata.get("documents") if isinstance(metadata.get("documents"), list) else []
    if documents:
        filenames = [
            _clean_text(document.get("filename") or document.get("original_path") or "source document")
            for document in documents
            if isinstance(document, dict)
        ]
    else:
        filenames = [_clean_text(metadata.get("filename") or metadata.get("original_path") or "source document")]
    filenames = [filename for filename in filenames if filename]
    count = len(filenames) if filenames else 1
    return {
        "combines_multiple_sources": count > 1,
        "combined_source_document_count": count,
        "combined_source_filenames": filenames or ["source document"],
    }


def _normalize_ai_analysis(value: dict[str, Any] | str) -> dict[str, Any]:
    raw_response = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    payload: dict[str, Any]
    if isinstance(value, dict):
        payload = value
    else:
        payload = _extract_json_object(value)
    issues = [_normalize_issue(issue) for issue in payload.get("issues", []) if isinstance(issue, dict)]
    return {
        "mode": payload.get("mode", "openai"),
        "document_type_detected": _clean_text(payload.get("document_type_detected", "")),
        "court_response_purpose": _clean_text(payload.get("court_response_purpose", "")),
        "issues": issues,
        "confidence_score": _bounded_float(payload.get("confidence_score"), 0.7),
        "raw_response": raw_response,
    }


def _normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    normalized = _issue(
        section=_valid_section(issue.get("section")),
        title=_clean_text(issue.get("issue_title") or issue.get("title") or "AI-detected issue"),
        location=_clean_text(issue.get("location_in_document") or issue.get("location") or "Not specified"),
        why=_clean_text(issue.get("why_it_matters") or "The issue may affect court acceptance or legal risk."),
        consequence=_clean_text(issue.get("possible_consequence") or "The court or requesting party may reject, disregard, or challenge the response."),
        correction=_clean_text(issue.get("recommended_correction") or "Review and correct before filing."),
        severity=_valid_severity(issue.get("severity")),
        confidence=_bounded_float(issue.get("confidence_score"), 0.7),
        attorney_review=bool(issue.get("attorney_review_strongly_recommended", True)),
    )
    normalized["source"] = "openai"
    return normalized


def _merge_issues(local_issues: list[dict[str, Any]], ai_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for issue in ai_issues + local_issues:
        key = (issue.get("section", ""), issue.get("issue_title", "").lower())
        if key in seen:
            continue
        seen.add(key)
        clean_issue = dict(issue)
        clean_issue.setdefault("supporting_local_rule_or_same_jurisdiction_source", NO_SAME_JURISDICTION_SUPPORT)
        merged.append(clean_issue)
    return merged


def _attach_same_jurisdiction_support(
    issues: list[dict[str, Any]],
    usable_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    supported: list[dict[str, Any]] = []
    support_text = NO_SAME_JURISDICTION_SUPPORT
    if usable_sources:
        first = usable_sources[0]
        support_text = (
            f"{first.get('case_title', 'CourtListener result')} "
            f"({first.get('court', 'court unknown')}, {first.get('date', 'date unknown')}) - "
            f"{first.get('reason', '')}"
        )
    for issue in issues:
        item = dict(issue)
        item["supporting_local_rule_or_same_jurisdiction_source"] = support_text
        supported.append(item)
    return supported


def _build_courtlistener_query(config: ReviewConfig, ai_analysis: dict[str, Any], issues: list[dict[str, Any]]) -> str:
    pieces = [
        config.state,
        config.city,
        config.county,
        config.court_name,
        config.court_level,
        config.request_type,
        ai_analysis.get("document_type_detected", ""),
        "local rule procedural compliance response",
    ]
    issue_terms = [issue.get("issue_title", "") for issue in issues[:4]]
    query = " ".join(_clean_text(piece) for piece in pieces + issue_terms if _clean_text(piece))
    return query[:900]


def _source_record(
    review_id: str,
    query: str,
    result: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    metadata = result.get("raw_metadata") if isinstance(result.get("raw_metadata"), dict) else {}
    court = _clean_text(result.get("court") or metadata.get("court") or metadata.get("court_id"))
    jurisdiction = _clean_text(result.get("jurisdiction") or metadata.get("jurisdiction") or court)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "review_id": review_id,
        "query": query,
        "case_title": _clean_text(result.get("title") or "Untitled CourtListener result"),
        "citation": _clean_text(result.get("citation", "")),
        "court": court,
        "jurisdiction": jurisdiction,
        "date": _clean_text(result.get("date") or metadata.get("date_filed") or metadata.get("dateFiled")),
        "url_or_source_id": _clean_text(result.get("absolute_url") or result.get("resource_uri") or metadata.get("resource_uri")),
        "snippet": _clean_text(result.get("snippet", ""))[:600],
        "usable": validation["usable"],
        "reason": validation["reason"],
    }


def _validation(usable: bool, title: str, reason: str) -> dict[str, Any]:
    return {
        "usable": usable,
        "case_title": title,
        "reason": reason,
    }


def _matches_selected_state_or_controlling_federal_scope(
    combined: str,
    config: ReviewConfig,
    scope: dict[str, str],
) -> dict[str, Any]:
    state_name, abbr = _state_name_and_abbr(config.state)
    normalized = combined.lower()
    if state_name and state_name.lower() in normalized:
        return {"ok": True, "reason": f"Result text matches selected state {state_name}."}
    if abbr and re.search(rf"\b{re.escape(abbr.lower())}\b", normalized):
        return {"ok": True, "reason": f"Result text matches selected state abbreviation {abbr}."}
    if config.is_federal() and scope["system"] == "federal":
        circuit = FEDERAL_CIRCUITS_BY_STATE.get(abbr.upper() if abbr else "")
        if circuit and circuit in normalized:
            return {"ok": True, "reason": f"Federal appellate authority controls federal courts in {state_name}."}
        if "supreme court of the united states" in normalized or "u.s. supreme court" in normalized or "scotus" in normalized:
            return {"ok": True, "reason": "U.S. Supreme Court authority controls federal courts."}
    return {"ok": False, "reason": f"Result does not match selected state {config.state}."}


def _matches_controlling_court_level(scope: dict[str, str], combined: str, config: ReviewConfig) -> dict[str, Any]:
    selected = config.court_level.strip().lower()
    level = scope["level"]
    if config.is_federal():
        if scope["system"] != "federal":
            return {"ok": False, "reason": "Result is not federal authority."}
        if selected == "federal appellate court" and level in {"federal_appellate", "federal_supreme"}:
            return {"ok": True, "reason": "Federal appellate or higher federal authority matched."}
        if selected == "federal district court" and level in {"federal_district", "federal_appellate", "federal_supreme"}:
            return {"ok": True, "reason": "Federal district or controlling higher federal authority matched."}
        if selected == "federal bankruptcy court" and level in {"federal_bankruptcy", "federal_district", "federal_appellate", "federal_supreme"}:
            return {"ok": True, "reason": "Federal bankruptcy or controlling higher federal authority matched."}
        return {"ok": False, "reason": f"Federal result level {level} does not match selected court level {config.court_level}."}

    if selected == "state supreme court":
        if level == "state_supreme":
            return {"ok": True, "reason": "State supreme authority matched."}
        return {"ok": False, "reason": "Only the same state supreme court can support a state supreme court review."}
    if selected == "state appellate court":
        if level in {"state_appellate", "state_supreme"}:
            return {"ok": True, "reason": "State appellate or controlling state supreme authority matched."}
        return {"ok": False, "reason": "Trial court authority does not control the selected state appellate review."}
    if selected in {"municipal", "county", "superior", "state trial court", "other"}:
        if level in {"state_trial", "state_appellate", "state_supreme", "local_trial", "unknown_state"}:
            return {"ok": True, "reason": "State/local trial or controlling higher state authority matched."}
    return {"ok": False, "reason": f"Result court level {level} does not match selected court level {config.court_level}."}


def _matches_trial_venue(scope: dict[str, str], combined: str, config: ReviewConfig) -> dict[str, Any]:
    level = scope["level"]
    normalized = combined.lower()
    if level in {"state_appellate", "state_supreme", "federal_appellate", "federal_supreme"}:
        return {"ok": True, "reason": "Higher controlling court does not require same city/county trial venue."}
    if config.is_federal():
        if config.court_name and _all_meaningful_tokens_in(config.court_name, normalized):
            return {"ok": True, "reason": "Federal court name matched."}
        if _contains_text(normalized, config.state) and not _contains_conflicting_trial_venue(normalized, config):
            return {"ok": True, "reason": "Federal trial authority matches selected state and no conflicting city/county was detected."}
        return {"ok": False, "reason": "Federal trial result does not match the selected federal venue closely enough."}
    if level in {"state_trial", "local_trial", "unknown_state"}:
        if config.court_name and _all_meaningful_tokens_in(config.court_name, normalized):
            return {"ok": True, "reason": "Same court name matched."}
        if _contains_text(normalized, config.city) or _contains_text(normalized, config.county):
            return {"ok": True, "reason": "Same city or county venue matched."}
        return {
            "ok": False,
            "reason": "Trial-level result comes from another or unverified city/county and cannot support this venue.",
        }
    return {"ok": True, "reason": "Venue validation passed."}


def _matches_request_relevance(combined: str, request_type: str) -> dict[str, Any]:
    normalized = combined.lower()
    terms = REQUEST_RELEVANCE_TERMS.get(request_type.strip().lower(), [])
    if not terms:
        terms = [term for term in re.split(r"\W+", request_type.lower()) if len(term) > 3]
    if any(term.lower() in normalized for term in terms):
        return {"ok": True, "reason": "Result is relevant to the configured request type or response category."}
    return {
        "ok": False,
        "reason": "Result does not appear relevant to the same request type, procedural issue, or document-response category.",
    }


def _result_scope(result: dict[str, Any]) -> dict[str, str]:
    text = _combined_result_text(result)
    if "supreme court of the united states" in text or "u.s. supreme court" in text or "scotus" in text:
        return {"system": "federal", "level": "federal_supreme"}
    if any(marker in text for marker in ["united states court of appeals", "u.s. court of appeals", "federal circuit"]):
        return {"system": "federal", "level": "federal_appellate"}
    if "bankruptcy" in text and any(marker in text for marker in ["united states", "u.s.", "federal"]):
        return {"system": "federal", "level": "federal_bankruptcy"}
    if any(marker in text for marker in ["united states district court", "u.s. district court", "federal district"]):
        return {"system": "federal", "level": "federal_district"}
    if "supreme court" in text:
        return {"system": "state", "level": "state_supreme"}
    if any(marker in text for marker in ["court of appeal", "court of appeals", "appellate division", "appellate court"]):
        return {"system": "state", "level": "state_appellate"}
    if any(marker in text for marker in ["superior court", "municipal court", "county court", "trial court"]):
        return {"system": "state", "level": "state_trial"}
    if any(marker in text for marker in ["city court", "justice court"]):
        return {"system": "state", "level": "local_trial"}
    return {"system": "state", "level": "unknown_state"}


def _combined_result_text(result: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("title", "citation", "court", "jurisdiction", "date", "docket_number", "snippet", "absolute_url", "resource_uri"):
        value = result.get(key)
        if value:
            values.append(str(value))
    metadata = result.get("raw_metadata")
    if isinstance(metadata, dict):
        values.append(json.dumps(metadata, sort_keys=True, default=str))
    return " ".join(values).lower()


def _detect_document_type(text: str, config: ReviewConfig) -> str:
    lower = text.lower()
    patterns = [
        ("Discovery response", ["interrogatories", "request for production", "request for admission"]),
        ("Motion opposition", ["opposition", "memorandum of points and authorities"]),
        ("Motion response", ["response to motion", "reply to motion"]),
        ("Notice deficiency correction", ["deficiency", "correction", "notice"]),
        ("Declaration", ["i declare", "under penalty of perjury"]),
        ("Proof of service", ["proof of service", "certificate of service"]),
    ]
    for label, terms in patterns:
        if any(term in lower for term in terms):
            return label
    return config.request_type or "Court response document"


def _detect_response_purpose(text: str, config: ReviewConfig) -> str:
    if _mentions_request_context(text, config):
        return f"Appears intended to answer a {config.request_type}."
    return f"Configured as a response to {config.request_type}; document purpose requires confirmation."


def _procedural_obligations(config: ReviewConfig) -> list[str]:
    request_type = config.request_type.strip().lower()
    obligations = [
        "Confirm exact local filing format, caption, page limits, attachments, and service requirements before filing.",
        "Confirm deadline calculation using the selected court's rules and any judge-specific order.",
    ]
    if "discovery" in request_type:
        obligations.extend([
            "Address each discovery request separately.",
            "Preserve objections and provide verification where required.",
        ])
    if "motion" in request_type:
        obligations.extend([
            "Include the requested relief or opposition position clearly.",
            "Support factual statements with admissible evidence and declarations.",
        ])
    if "clerk" in request_type or "deficiency" in request_type:
        obligations.append("Cure each listed deficiency and include any required corrected filing label.")
    if "judge" in request_type:
        obligations.append("Answer each directive in the judge's order and avoid expanding beyond the requested response without reason.")
    return obligations


def _issue(
    section: str,
    title: str,
    location: str,
    why: str,
    consequence: str,
    correction: str,
    severity: str,
    confidence: float,
    attorney_review: bool,
) -> dict[str, Any]:
    return {
        "section": _valid_section(section),
        "severity": _valid_severity(severity),
        "issue_title": title,
        "location_in_document": location,
        "why_it_matters": why,
        "possible_consequence": consequence,
        "supporting_local_rule_or_same_jurisdiction_source": NO_SAME_JURISDICTION_SUPPORT,
        "recommended_correction": correction,
        "confidence_score": _bounded_float(confidence, 0.7),
        "attorney_review_strongly_recommended": attorney_review,
        "source": "local_document_review",
    }


def _valid_section(value: Any) -> str:
    text = _clean_text(value)
    return text if text in REPORT_SECTION_TITLES else "Procedural Risks"


def _valid_severity(value: Any) -> str:
    text = _clean_text(value).title()
    return text if text in {"Critical", "High", "Medium", "Low", "Informational"} else "Medium"


def _bounded_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number > 1:
        number = number / 100
    return round(max(0.0, min(1.0, number)), 2)


def _extract_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _has_caption(text: str, config: ReviewConfig) -> bool:
    heading = text[:2500].lower()
    signals = [
        "superior court",
        "municipal court",
        "county court",
        "district court",
        "bankruptcy court",
        "court of appeal",
        "supreme court",
        "case no",
        "case number",
    ]
    if any(signal in heading for signal in signals):
        return True
    return bool(config.court_name and config.court_name.lower() in heading)


def _mentions_request_context(text: str, config: ReviewConfig) -> bool:
    lower = text.lower()
    terms = REQUEST_RELEVANCE_TERMS.get(config.request_type.lower(), [])
    if any(term in lower for term in terms):
        return True
    if config.judge_name and config.judge_name.lower() in lower:
        return True
    if config.attorney_or_requesting_party_name and config.attorney_or_requesting_party_name.lower() in lower:
        return True
    return False


def _has_unsupported_assertions(text: str) -> bool:
    lower = text.lower()
    assertion_markers = ["clearly", "obviously", "undisputed", "all damages", "never", "always", "bad faith"]
    support_markers = ["exhibit", "declaration", "attached", "see", "pursuant", "rule", "section", "§"]
    return any(marker in lower for marker in assertion_markers) and not any(marker in lower for marker in support_markers)


def _risky_language_location(text: str) -> str:
    patterns = [
        r"\bi admit\b.{0,120}",
        r"\bwe admit\b.{0,120}",
        r"\bi failed\b.{0,120}",
        r"\bwe failed\b.{0,120}",
        r"\bunable to comply\b.{0,120}",
        r"\bi will pay\b.{0,120}",
        r"\bdefault\b.{0,120}",
        r"\bsanctions?\b.{0,120}",
        r"\bwaive\b.{0,120}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(0).strip()[:180]
    return ""


def _mentions_exhibits_without_attachments(text: str) -> bool:
    lower = text.lower()
    references_exhibit = bool(re.search(r"\bexhibit\s+[a-z0-9]", lower))
    has_attachment_language = any(term in lower for term in ["attached as exhibit", "exhibit list", "index of exhibits"])
    return references_exhibit and not has_attachment_language


def _has_signature(text: str) -> bool:
    lower = text.lower()
    return any(term in lower[-2500:] for term in ["signature", "/s/", "respectfully submitted", "dated:", "date:"])


def _has_proof_of_service(text: str) -> bool:
    lower = text.lower()
    return "proof of service" in lower or "certificate of service" in lower or "i served" in lower


def _detect_name_context_mismatch(text: str, config: ReviewConfig) -> str:
    lower = text.lower()
    missing: list[str] = []
    if config.court_name and config.court_name.lower() not in lower:
        missing.append("court name")
    if config.judge_name and config.judge_name.lower() not in lower:
        missing.append("judge name")
    if config.attorney_or_requesting_party_name and config.attorney_or_requesting_party_name.lower() not in lower:
        missing.append("attorney/requesting party name")
    return ", ".join(missing)


def _extract_docx_text(path: Path) -> tuple[str, str, str, list[str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        text_parts = [node.text for node in root.iter() if node.text]
        return "\n".join(text_parts), "extracted", "docx_xml", []
    except Exception as exc:
        return "", "extraction_failed", "docx_xml", [f"DOCX text extraction failed: {str(exc)[:160]}"]


def _extract_pdf_text(path: Path) -> tuple[str, str, str, list[str]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages]
        text = "\n\n".join(pages).strip()
        status = "extracted" if text else "no_text_extracted"
        return text, status, "pypdf", [] if text else ["PDF did not contain extractable text."]
    except Exception as exc:
        text, status, _method, warnings = _best_effort_text(path)
        warnings.append(f"PDF text extraction library unavailable or failed: {str(exc)[:160]}")
        return text, "best_effort_binary_text" if text else "pdf_text_unavailable", "best_effort_pdf", warnings


def _best_effort_text(path: Path) -> tuple[str, str, str, list[str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return "", "extraction_failed", "best_effort", [str(exc)]
    decoded = raw.decode("utf-8", errors="replace")
    printable = "".join(char if char.isprintable() or char in "\r\n\t" else " " for char in decoded)
    compact = re.sub(r"[ \t]{2,}", " ", printable)
    if len(compact.strip()) < 40:
        return "", "unsupported_binary", "best_effort", ["File type is not text-searchable with available dependencies."]
    return compact[:250000], "best_effort_text", "best_effort", ["File was decoded with best-effort text extraction."]


def _write_manifest(
    manifest_path: Path,
    review_id: str,
    report: dict[str, Any],
    extraction: dict[str, Any],
    report_paths: dict[str, str],
) -> None:
    _append_jsonl(
        manifest_path,
        {
            "timestamp": report.get("generated_at"),
            "review_id": review_id,
            "filename": extraction["metadata"].get("filename"),
            "file_hash_sha256": extraction["metadata"].get("file_hash_sha256"),
            "report_paths": report_paths,
            "review_configuration": extraction["metadata"].get("review_configuration"),
        },
    )


def _storage_paths(storage_root: str | Path | None) -> dict[str, Path]:
    root = Path(storage_root) if storage_root else Path.cwd() / "standalone_reviews" / "court_response_compliance"
    return {
        "root": root,
        "input": root / "input",
        "reports": root / "reports",
        "generated_documents": root / "generated_documents",
        "rejected_sources": root / "rejected_sources",
        "logs": root / "logs",
        "manifest": root / "review_manifest.jsonl",
        "queries": root / "courtlistener_queries.jsonl",
        "rejected_log": root / "rejected_sources.jsonl",
    }


def _ensure_storage(storage: dict[str, Path]) -> None:
    for key in ("root", "input", "reports", "generated_documents", "rejected_sources", "logs"):
        storage[key].mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _normalize_document_paths(document_path: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(document_path, (str, Path)):
        if isinstance(document_path, str) and "\n" in document_path:
            raw_paths = [part.strip() for part in document_path.splitlines() if part.strip()]
        else:
            raw_paths = [document_path]
    else:
        raw_paths = list(document_path)
    return [Path(path).expanduser() for path in raw_paths if str(path).strip()]


def _build_review_id(path: Path, config: ReviewConfig, timestamp: datetime, *, document_count: int = 1) -> str:
    seed = f"{path.name}|count:{document_count}|{config.state}|{config.city}|{config.court_level}|{config.request_type}|{timestamp.isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{digest}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return safe or "document"


def _state_name_and_abbr(value: str) -> tuple[str, str]:
    cleaned = value.strip().lower()
    if len(cleaned) == 2:
        abbr = cleaned.upper()
        return STATE_NAMES_BY_ABBR.get(abbr, abbr), abbr
    abbr = STATE_ALIASES.get(cleaned, "")
    return cleaned.title(), abbr


def _contains_text(haystack: str, needle: str) -> bool:
    cleaned = needle.strip().lower()
    return bool(cleaned and cleaned in haystack)


def _contains_conflicting_trial_venue(normalized: str, config: ReviewConfig) -> bool:
    if _contains_text(normalized, config.city) or _contains_text(normalized, config.county) or _contains_text(normalized, config.court_name):
        return False
    selected_terms = [_clean_text(config.city).lower(), _clean_text(config.county).lower()]
    selected_terms = [term for term in selected_terms if term]
    if any(term and term in normalized for term in selected_terms):
        return False
    return any(marker in normalized for marker in [" county superior court", " municipal court", " city court"])


def _all_meaningful_tokens_in(value: str, normalized: str) -> bool:
    tokens = [
        token
        for token in re.split(r"\W+", value.lower())
        if len(token) > 2 and token not in {"the", "and", "for", "court", "county", "superior", "district"}
    ]
    return bool(tokens) and all(token in normalized for token in tokens)


def _issues_for_section(issues: list[dict[str, Any]], section: str) -> list[dict[str, Any]]:
    return [issue for issue in issues if issue.get("section") == section]


def _recommended_corrections(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "issue_title": issue.get("issue_title"),
            "severity": issue.get("severity"),
            "recommended_correction": issue.get("recommended_correction"),
            "attorney_review_strongly_recommended": issue.get("attorney_review_strongly_recommended", True),
        }
        for issue in issues
    ]


def _overall_confidence(
    issues: list[dict[str, Any]],
    ai_analysis: dict[str, Any],
    courtlistener: dict[str, Any],
) -> float:
    scores = [float(issue.get("confidence_score", 0.7)) for issue in issues]
    if ai_analysis.get("confidence_score") is not None:
        scores.append(float(ai_analysis.get("confidence_score", 0.7)))
    if courtlistener.get("usable_sources"):
        scores.append(0.82)
    elif courtlistener.get("status") == "unavailable":
        scores.append(0.62)
    return round(sum(scores) / len(scores), 2) if scores else 0.65


def _markdown_lines_for_value(value: Any) -> list[str]:
    if value is None or value == "":
        return ["None identified."]
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        return [str(value)]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"- {key}: {json.dumps(item, sort_keys=True, default=str)}")
            else:
                lines.append(f"- {key}: {item}")
        return lines or ["None identified."]
    if isinstance(value, list):
        if not value:
            return ["None identified."]
        lines = []
        for item in value:
            if isinstance(item, dict):
                title = item.get("issue_title") or item.get("case_title") or item.get("title") or "Item"
                detail = item.get("recommended_correction") or item.get("reason") or item.get("why_it_matters") or ""
                severity = item.get("severity")
                prefix = f"- {title}"
                if severity:
                    prefix += f" ({severity})"
                lines.append(f"{prefix}: {detail}")
            else:
                lines.append(f"- {item}")
        return lines
    return [str(value)]


def _write_simple_pdf(path: Path, text: str) -> None:
    safe_lines = _pdf_escape(text).splitlines()
    page_lines = [line[:96] for line in safe_lines[:90]]
    content_lines = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
    for line in page_lines:
        content_lines.append(f"({line}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content.extend(obj)
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(content))


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
