from __future__ import annotations
import json
import re
from typing import Any

CITATION_PATTERNS = {
    "statute": re.compile(r"^[\w\.\s\d\§\-:\(\),]+$"),
    "case": re.compile(r"^[\w\s\.\-]*\d+[\w\s\.\-]*\d+$", re.IGNORECASE),
    "rule": re.compile(r"^[\w\s\.\d\§\-:\(\),]+$"),
    "local rule": re.compile(r"^[\w\s\.\d\§\-:\(\),]+$"),
}


def build_openai_prompt(context: str, instructions: str) -> str:
    return (
        "Context:\n" + context + "\n\n"
        "Instructions:\n" + instructions + "\n\n"
        "Use only the verified facts and authorities provided. Do not invent citations, cases, statutes, holdings, or sources."
    )


def validate_citation_format(authority_type: str, citation: str) -> bool:
    pattern = CITATION_PATTERNS.get(authority_type.lower(), re.compile(r"^.+$"))
    return bool(citation and pattern.match(citation.strip()))


def validate_source_url(source_url: str) -> bool:
    if not source_url:
        return False
    return source_url.startswith("http://") or source_url.startswith("https://")


def validate_excerpt(source_text_excerpt: str) -> bool:
    return bool(source_text_excerpt and len(source_text_excerpt.strip()) >= 20)


def validate_jurisdiction_match(authority_jurisdiction: str, case_jurisdiction: str) -> bool:
    authority_value = authority_jurisdiction.strip().lower() if authority_jurisdiction else ""
    case_value = case_jurisdiction.strip().lower() if case_jurisdiction else ""
    if not authority_value:
        return False
    if not case_value:
        return True
    return authority_value in case_value or case_value in authority_value


def validate_authority_payload(authority: dict[str, Any], case_jurisdiction: str | None = None) -> dict[str, bool]:
    results: dict[str, bool] = {}
    results["citation_format"] = validate_citation_format(authority.get("authority_type", ""), authority.get("citation", ""))
    results["source_url"] = validate_source_url(authority.get("source_url", ""))
    results["excerpt"] = validate_excerpt(authority.get("source_text_excerpt", ""))
    results["jurisdiction_match"] = validate_jurisdiction_match(authority.get("jurisdiction", ""), case_jurisdiction or "")
    results["year_present"] = bool(authority.get("year"))
    results["title_present"] = bool(authority.get("title", ""))
    results["authority_type_present"] = bool(authority.get("authority_type", ""))
    results["verified_ready"] = all(results.values())
    return results


def validate_local_rule(authority: dict[str, Any], case_jurisdiction: str | None = None) -> dict[str, bool]:
    result = validate_authority_payload(authority, case_jurisdiction)
    result["authority_type_valid"] = authority.get("authority_type", "").lower() == "local rule"
    return result


def validate_procedural_deadline(deadline: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    checks["trigger_date"] = bool(deadline.get("trigger_date"))
    checks["source_url"] = validate_source_url(deadline.get("source_url", ""))
    checks["rule_reference"] = bool(deadline.get("rule_reference"))
    checks["description"] = bool(deadline.get("description", ""))
    checks["verified_ready"] = all(checks.values())
    return checks


def validate_quotation(quotation: dict[str, Any]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    results["quote_text"] = bool(quotation.get("quote_text", ""))
    results["source_text_excerpt"] = validate_excerpt(quotation.get("source_text_excerpt", ""))
    results["source_url"] = validate_source_url(quotation.get("source_url", ""))
    results["verified_ready"] = all(results.values())
    return results
