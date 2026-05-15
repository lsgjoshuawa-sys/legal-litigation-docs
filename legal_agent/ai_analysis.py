from __future__ import annotations

from typing import Any

from .case_profile import build_ai_context, build_case_profile
from .courtlistener_access import validate_output_citations
from .openai_client import analyze_text, get_stored_api_key
from .resource_throttle import get_throttling_agent


AI_ANALYSIS_INSTRUCTIONS = """
Produce a litigation workup from the stored case profile.

Requirements:
- Use only the stored case profile, recorded evidence, recorded research, and stored authorities.
- Do not invent citations, statutes, rules, holdings, quotations, or source URLs.
- Separate potential arguments, potential defenses, evidence gaps, and potentially adverse authority.
- Cite only authorities that appear in the verified_authorities list.
- If the stored authorities are not enough, say what authority research is needed instead of fabricating citations.
- Treat similar-case comparisons as valid only when they come from stored CourtListener/public metadata research.
- Do not claim a presented case is real, determined, or factually accurate unless a CourtListener validation result says public metadata and determination were confirmed.
- Treat confidence as a qualitative review aid, not a guarantee of legal correctness.
- Mention CourtListener citation guardrail status when available.
"""


def generate_argument_analysis(case_id: int, db_path: str | None = None) -> dict[str, Any]:
    profile = build_case_profile(case_id, db_path)
    if profile.get("error"):
        return {"ok": False, "analysis": profile["error"], "profile": profile}

    throttling_agent = get_throttling_agent()
    throttle_report = throttling_agent.report()
    citation_validation = validate_output_citations(profile.get("verified_authorities", []))
    api_key = get_stored_api_key(db_path)
    context = build_ai_context(case_id, db_path)
    if not api_key:
        return {
            "ok": True,
            "mode": "local",
            "analysis": _local_analysis(profile, citation_validation, throttle_report),
            "citation_validation": citation_validation,
            "throttle": throttle_report,
            "profile": profile,
        }

    try:
        analysis = analyze_text(api_key, context, AI_ANALYSIS_INSTRUCTIONS)
        return {
            "ok": True,
            "mode": "openai",
            "analysis": analysis,
            "citation_validation": citation_validation,
            "throttle": throttle_report,
            "profile": profile,
        }
    except ValueError as exc:
        return {
            "ok": False,
            "mode": "openai_error",
            "analysis": f"AI analysis could not be completed: {exc}\n\n" + _local_analysis(profile, citation_validation, throttle_report),
            "citation_validation": citation_validation,
            "throttle": throttle_report,
            "profile": profile,
        }


def _local_analysis(profile: dict[str, Any], citation_validation: dict[str, Any], throttle_report: dict[str, Any]) -> str:
    budget = throttle_report.get("budget", {})
    lines = [
        "# AI Argument Analysis",
        "",
        "OpenAI analysis is not available, so this local workup itemizes the stored case profile and verified authorities without inventing citations.",
        "",
        "## Throttle Status",
        f"- Enabled: {budget.get('enabled', True)}",
        f"- AI calls/minute: {budget.get('ai_requests_per_minute', 'unknown')}",
        f"- AI context limit: {budget.get('ai_max_context_chars', 'unknown')} characters",
        f"- Citation checks/run: {budget.get('citation_checks_per_run', 'unknown')}",
        "",
        "## Potential Arguments",
    ]
    claims = profile.get("claims", [])
    evidence = profile.get("evidence", [])
    authorities = profile.get("verified_authorities", [])
    if claims:
        for claim in claims:
            lines.append(f"- {claim.get('claim_name', 'Unspecified claim')}: review against recorded evidence and required elements.")
    else:
        lines.append("- No claims or defenses have been recorded yet.")

    lines.extend(["", "## Potential Defenses / Challenges"])
    if evidence:
        lines.append("- Evaluate admissibility, foundation, authentication, and whether each evidence item supports a required element.")
    else:
        lines.append("- No evidence has been recorded; evidence sufficiency remains unresolved.")
    if not authorities:
        lines.append("- No verified authorities are stored; legal support and adverse authority research are still needed.")

    lines.extend(["", "## Verified Authorities Available for Citation"])
    if authorities:
        for authority in authorities:
            citation = authority.get("citation") or "No citation"
            treatment = authority.get("treatment_status") or "unknown"
            lines.append(f"- {authority.get('title', 'Untitled Authority')} ({citation}) - treatment: {treatment}")
    else:
        lines.append("- None.")

    lines.extend(["", "## CourtListener Citation Guardrail"])
    lines.append(citation_validation.get("message", "CourtListener citation validation did not run."))
    lines.append(f"- Status: {citation_validation.get('status', 'unknown')}")
    lines.append(f"- Checked: {citation_validation.get('checked', False)}")

    lines.extend(["", "## Similar Case / Determination Guardrail"])
    lines.append("- Use CourtListener Research with an explicit public-law query to find similar cases.")
    lines.append("- A case should only be treated as real and determined when public metadata confirms a match and determination status.")

    lines.extend(["", "## Reliability Note"])
    lines.append("No system can guarantee less than 1% doubt that legal citations apply to a specific matter. Treat this as a research and drafting aid requiring attorney review.")
    return "\n".join(lines)
