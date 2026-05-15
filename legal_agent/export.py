from __future__ import annotations
import json
from typing import Any

from . import db
from .intake import get_case, generate_timeline
from .jurisdiction import get_procedural_rules
from .evidence import evidence_review
from .authority_validation import get_verified_authorities, get_unverified_authorities
from .courtlistener_access import validate_output_citations
from .drafting import generate_outline, save_document, get_document
from .observability import performance_checkpoint
from .vulnerability import analyze_vulnerabilities
from .safety import legal_disclaimer


def export_case(case_id: int, export_format: str = "markdown", output_path: str | None = None, db_path: str | None = None) -> str:
    with performance_checkpoint(
        "export_case",
        context={"case_id": case_id, "export_format": export_format, "output_path_supplied": bool(output_path)},
        slow_ms=1500,
    ):
        case = get_case(case_id, db_path)
        if not case:
            raise ValueError("Case not found")
        timeline = generate_timeline(case_id, db_path)
        rule_data = get_procedural_rules(case_id, db_path)
        evidence_data = evidence_review(case_id, db_path)
        verified = get_verified_authorities(case_id, db_path)
        unverified = get_unverified_authorities(case_id, db_path)
        citation_validation = validate_output_citations(verified)
        outline = generate_outline(case_id, "filing checklist", db_path)
        vulnerabilities = analyze_vulnerabilities(case_id, db_path=db_path)
        if export_format == "json":
            payload = {
                "case": case.to_dict(),
                "procedural_rules": rule_data,
                "timeline": [item.to_dict() for item in timeline],
                "evidence_review": evidence_data,
                "verified_authorities": verified,
                "courtlistener_citation_validation": citation_validation,
                "unverified_research_leads": unverified,
                "outline": outline,
                "vulnerabilities": vulnerabilities,
                "disclaimer": legal_disclaimer(),
            }
            output = json.dumps(payload, indent=2)
        else:
            lines = [f"# Case Export: {case.title}", ""]
            lines.append("## Case Summary")
            lines.append(case.description or "No description provided.")
            lines.append("")
            lines.append("## Jurisdiction")
            lines.append(case.jurisdiction or "Unclear")
            lines.append("")
            lines.append("## Procedural Rule Set")
            if rule_data.get("rules"):
                for rule in rule_data["rules"]:
                    lines.append(f"- {rule}")
            else:
                lines.append(rule_data.get("note", "No rule set identified."))
            lines.append("")
            lines.append("## Action Timeline")
            if timeline:
                for item in timeline:
                    lines.append(f"- {item.due_date or 'unknown'}: {item.action_text} ({item.status})")
            else:
                lines.append("No action items recorded.")
            lines.append("")
            lines.append("## Evidence Review")
            for claim in evidence_data.get("claim_reviews", []):
                lines.append(f"### {claim['claim_name']}")
                lines.append(f"- Required elements: {claim['required_elements']}")
                lines.append(f"- Supported: {claim['supported_elements']}")
                lines.append(f"- Missing: {claim['missing_elements']}")
                if claim["supplemental_items"]:
                    lines.append("- Supplemental evidence:")
                    for item in claim["supplemental_items"]:
                        lines.append(f"  - {item}")
            lines.append("")
            lines.append("## Verified Authorities")
            if verified:
                for auth in verified:
                    lines.append(f"- [{auth['id']}] {auth['title']} ({auth['citation']})")
            else:
                lines.append("No verified authorities stored.")
            lines.append("")
            lines.append("## CourtListener Citation Guardrail")
            lines.append(citation_validation.get("message", "CourtListener citation validation did not run."))
            lines.append(f"- Status: {citation_validation.get('status', 'unknown')}")
            lines.append(f"- Checked: {citation_validation.get('checked', False)}")
            for result in citation_validation.get("results", []):
                lines.append(f"- {result.get('citation', 'unknown citation')}: {result.get('status')} ({result.get('match_count', 0)} match(es))")
            lines.append("")
            lines.append("## Unverified Research Leads")
            if unverified:
                for auth in unverified:
                    lines.append(f"- [{auth['id']}] {auth['title']} ({auth['citation']}) - UNVERIFIED")
            else:
                lines.append("No unverified research leads recorded.")
            lines.append("")
            lines.append("## Filing Checklist Outline")
            for section in outline.get("outline", []):
                lines.append(f"- {section}")
            lines.append("")
            lines.append("## Vulnerability Analysis")
            for issue in vulnerabilities.get("issues", []):
                lines.append(f"- {issue['issue_type']}: {issue['description']} ({issue['risk_level']})")
            lines.append("")
            lines.append("## Disclaimer")
            lines.append(legal_disclaimer())
            output = "\n".join(lines)
        if output_path:
            with performance_checkpoint(
                "export_file_write",
                context={"export_format": export_format, "output_path_supplied": True},
                slow_ms=500,
            ):
                with open(output_path, "w", encoding="utf-8") as handle:
                    handle.write(output)
        return output
