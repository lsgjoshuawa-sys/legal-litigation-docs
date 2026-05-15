from __future__ import annotations
import argparse
import json
import sys

from . import db
from .authority_validation import add_authority, get_authority, verify_authority
from .case_tracks import LEGAL_TRACK_CHOICES
from .drafting import generate_outline, save_document
from .evidence import element_checklist, evidence_review
from .intake import (
    add_action_item,
    add_claim,
    add_evidence,
    add_fact,
    add_party,
    create_case,
    generate_timeline,
    get_case,
    request_due_dates,
)
from .db import init_db
from .jurisdiction import classify_case, get_procedural_rules
from .research import add_research_log
from .treatment import get_treatment_status, set_treatment_status
from .export import export_case
from .gui import run_gui
from .vulnerability import analyze_vulnerabilities


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2))


def _ensure_case_exists(case_id: int, db_path: str | None) -> None:
    case = get_case(case_id, db_path)
    if not case:
        print(f"Case {case_id} not found.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Legal operations and litigation drafting assistant CLI")
    parser.add_argument("--db", default=None, help="SQLite database path. Defaults to legal_agent.db in cwd.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init-db", help="Initialize the local SQLite database")

    new_case = subparsers.add_parser("new-case", help="Create a new case")
    new_case.add_argument("--title", required=True)
    new_case.add_argument("--description", default="")
    new_case.add_argument(
        "--legal-track",
        default="",
        help="Procedure track purpose. Accepted legacy aliases: A, B, C. Current choices: "
        + "; ".join(track for track in LEGAL_TRACK_CHOICES if track),
    )
    new_case.add_argument("--jurisdiction", default="")
    new_case.add_argument("--court-name", default="")
    new_case.add_argument("--court-level", default="")
    new_case.add_argument("--district", default="")
    new_case.add_argument("--judge", default="")
    new_case.add_argument("--department", default="")
    new_case.add_argument("--filing-status", default="")

    add_party_cmd = subparsers.add_parser("add-party", help="Add a party to a case")
    add_party_cmd.add_argument("--case-id", type=int, required=True)
    add_party_cmd.add_argument("--name", required=True)
    add_party_cmd.add_argument("--role", default="")
    add_party_cmd.add_argument("--type", default="")
    add_party_cmd.add_argument("--notes", default="")

    add_fact_cmd = subparsers.add_parser("add-fact", help="Add a fact to a case")
    add_fact_cmd.add_argument("--case-id", type=int, required=True)
    add_fact_cmd.add_argument("--fact-text", required=True)
    add_fact_cmd.add_argument("--date", default="")
    add_fact_cmd.add_argument("--source-evidence-id", type=int, default=None)
    add_fact_cmd.add_argument("--relevance", default="")

    add_claim_cmd = subparsers.add_parser("add-claim", help="Add a claim or defense")
    add_claim_cmd.add_argument("--case-id", type=int, required=True)
    add_claim_cmd.add_argument("--claim-name", required=True)
    add_claim_cmd.add_argument("--claim-type", default="")
    add_claim_cmd.add_argument("--jurisdiction-basis", default="")
    add_claim_cmd.add_argument("--required-elements", default="[]")
    add_claim_cmd.add_argument("--status", default="")
    add_claim_cmd.add_argument("--notes", default="")

    add_evidence_cmd = subparsers.add_parser("add-evidence", help="Add an evidence item to a case")
    add_evidence_cmd.add_argument("--case-id", type=int, required=True)
    add_evidence_cmd.add_argument("--title", required=True)
    add_evidence_cmd.add_argument("--evidence-type", default="")
    add_evidence_cmd.add_argument("--description", default="")
    add_evidence_cmd.add_argument("--file-path", default="")
    add_evidence_cmd.add_argument("--date-obtained", default="")
    add_evidence_cmd.add_argument("--supports-claims", default="[]")
    add_evidence_cmd.add_argument("--admissibility-notes", default="")
    add_evidence_cmd.add_argument("--weakness-notes", default="")

    add_action_cmd = subparsers.add_parser("add-action", help="Add an action item")
    add_action_cmd.add_argument("--case-id", type=int, required=True)
    add_action_cmd.add_argument("--action-text", required=True)
    add_action_cmd.add_argument("--category", default="")
    add_action_cmd.add_argument("--due-date", default="")
    add_action_cmd.add_argument("--dependency", default="")
    add_action_cmd.add_argument("--status", default="open")
    add_action_cmd.add_argument("--notes", default="")

    subparsers.add_parser("request-due-dates", help="Prompt for missing due dates").add_argument("--case-id", type=int, required=True)
    subparsers.add_parser("timeline", help="Generate litigation timeline").add_argument("--case-id", type=int, required=True)
    subparsers.add_parser("classify", help="Classify jurisdiction").add_argument("--case-id", type=int, required=True)
    subparsers.add_parser("procedural-rules", help="Identify applicable procedural rule set").add_argument("--case-id", type=int, required=True)

    add_authority_cmd = subparsers.add_parser("add-authority", help="Add an authority to a case")
    add_authority_cmd.add_argument("--case-id", type=int, required=True)
    add_authority_cmd.add_argument("--authority-type", default="")
    add_authority_cmd.add_argument("--title", required=True)
    add_authority_cmd.add_argument("--citation", default="")
    add_authority_cmd.add_argument("--jurisdiction", default="")
    add_authority_cmd.add_argument("--court", default="")
    add_authority_cmd.add_argument("--year", type=int, default=None)
    add_authority_cmd.add_argument("--source-url", default="")
    add_authority_cmd.add_argument("--source-text-excerpt", default="")
    add_authority_cmd.add_argument("--treatment-status", default="unknown")
    add_authority_cmd.add_argument("--treatment-notes", default="")
    add_authority_cmd.add_argument("--verified", action="store_true")

    verify_authority_cmd = subparsers.add_parser("verify-authority", help="Verify an authority")
    verify_authority_cmd.add_argument("--authority-id", type=int, required=True)

    treatment_cmd = subparsers.add_parser("treatment-check", help="View or set treatment status")
    treatment_cmd.add_argument("--authority-id", type=int, required=True)
    treatment_cmd.add_argument("--status", default="")
    treatment_cmd.add_argument("--notes", default="")

    element_cmd = subparsers.add_parser("element-checklist", help="Build claim element checklist")
    element_cmd.add_argument("--case-id", type=int, required=True)
    element_cmd.add_argument("--claim-id", type=int, required=True)

    subparsers.add_parser("evidence-review", help="Compare evidence against required elements").add_argument("--case-id", type=int, required=True)

    outline_cmd = subparsers.add_parser("outline-document", help="Generate document outline")
    outline_cmd.add_argument("--case-id", type=int, required=True)
    outline_cmd.add_argument("--type", required=True)

    draft_cmd = subparsers.add_parser("draft-document", help="Generate draft document structure")
    draft_cmd.add_argument("--case-id", type=int, required=True)
    draft_cmd.add_argument("--type", required=True)

    vuln_cmd = subparsers.add_parser("vulnerability-check", help="Analyze vulnerability")
    vuln_cmd.add_argument("--case-id", type=int, required=True)
    vuln_cmd.add_argument("--document-id", type=int, default=None)

    filing_cmd = subparsers.add_parser("filing-checklist", help="Generate filing-readiness checklist")
    filing_cmd.add_argument("--case-id", type=int, required=True)

    export_cmd = subparsers.add_parser("export", help="Export output as Markdown, JSON, or TXT")
    export_cmd.add_argument("--case-id", type=int, required=True)
    export_cmd.add_argument("--format", default="markdown", choices=["markdown", "json", "txt"])
    export_cmd.add_argument("--output", default="")

    args = parser.parse_args()
    db_path = args.db

    if args.command == "init-db":
        db.init_db(db_path)
        print("Database initialized.")

    elif args.command == "new-case":
        case_id = create_case(
            title=args.title,
            description=args.description,
            legal_track=args.legal_track,
            jurisdiction=args.jurisdiction,
            court_name=args.court_name,
            court_level=args.court_level,
            district=args.district,
            judge=args.judge,
            department=args.department,
            filing_status=args.filing_status,
            db_path=db_path,
        )
        print(f"Created case {case_id}.")

    elif args.command == "add-party":
        _ensure_case_exists(args.case_id, db_path)
        party_id = add_party(args.case_id, args.name, args.role, args.type, args.notes, db_path)
        print(f"Added party {party_id}.")

    elif args.command == "add-fact":
        _ensure_case_exists(args.case_id, db_path)
        fact_id = add_fact(args.case_id, args.fact_text, args.date, args.source_evidence_id, args.relevance, db_path)
        print(f"Added fact {fact_id}.")

    elif args.command == "add-claim":
        _ensure_case_exists(args.case_id, db_path)
        claim_id = add_claim(
            args.case_id,
            args.claim_name,
            args.claim_type,
            args.jurisdiction_basis,
            args.required_elements,
            args.status,
            args.notes,
            db_path,
        )
        print(f"Added claim {claim_id}.")

    elif args.command == "add-evidence":
        _ensure_case_exists(args.case_id, db_path)
        evidence_id = add_evidence(
            args.case_id,
            args.title,
            args.evidence_type,
            args.description,
            args.file_path,
            args.date_obtained,
            args.supports_claims,
            args.admissibility_notes,
            args.weakness_notes,
            db_path,
        )
        print(f"Added evidence {evidence_id}.")

    elif args.command == "add-action":
        _ensure_case_exists(args.case_id, db_path)
        action_id = add_action_item(
            args.case_id,
            args.action_text,
            args.category,
            args.due_date,
            args.dependency,
            args.status,
            args.notes,
            db_path,
        )
        print(f"Added action item {action_id}.")

    elif args.command == "request-due-dates":
        _ensure_case_exists(args.case_id, db_path)
        updated = request_due_dates(args.case_id, db_path)
        _print_json(updated)

    elif args.command == "timeline":
        _ensure_case_exists(args.case_id, db_path)
        timeline = generate_timeline(args.case_id, db_path)
        _print_json(timeline)

    elif args.command == "classify":
        _ensure_case_exists(args.case_id, db_path)
        result = classify_case(args.case_id, db_path)
        _print_json(result)

    elif args.command == "procedural-rules":
        _ensure_case_exists(args.case_id, db_path)
        result = get_procedural_rules(args.case_id, db_path)
        _print_json(result)

    elif args.command == "add-authority":
        _ensure_case_exists(args.case_id, db_path)
        authority_id = add_authority(
            args.case_id,
            args.authority_type,
            args.title,
            args.citation,
            args.jurisdiction,
            args.court,
            args.year,
            args.source_url,
            args.source_text_excerpt,
            args.treatment_status,
            args.treatment_notes,
            args.verified,
            db_path,
        )
        print(f"Added authority {authority_id}.")

    elif args.command == "verify-authority":
        ok = verify_authority(args.authority_id, True, db_path)
        print("Verified." if ok else "Authority not found.")

    elif args.command == "treatment-check":
        if args.status:
            try:
                updated = set_treatment_status(args.authority_id, args.status, args.notes, db_path)
                print("Treatment status updated." if updated else "Authority not found.")
            except ValueError as exc:
                print(str(exc))
                sys.exit(1)
        else:
            status = get_treatment_status(args.authority_id, db_path)
            _print_json(status or {"error": "Authority not found."})

    elif args.command == "element-checklist":
        _ensure_case_exists(args.case_id, db_path)
        checklist = element_checklist(args.case_id, args.claim_id, db_path)
        _print_json(checklist)

    elif args.command == "evidence-review":
        _ensure_case_exists(args.case_id, db_path)
        review = evidence_review(args.case_id, db_path)
        _print_json(review)

    elif args.command == "outline-document":
        _ensure_case_exists(args.case_id, db_path)
        outline = generate_outline(args.case_id, args.type, db_path)
        _print_json(outline)

    elif args.command == "draft-document":
        _ensure_case_exists(args.case_id, db_path)
        draft = save_document(args.case_id, args.type, db_path)
        _print_json(draft)

    elif args.command == "vulnerability-check":
        _ensure_case_exists(args.case_id, db_path)
        vulnerabilities = analyze_vulnerabilities(args.case_id, args.document_id, db_path)
        _print_json(vulnerabilities)

    elif args.command == "filing-checklist":
        _ensure_case_exists(args.case_id, db_path)
        outline = generate_outline(args.case_id, "filing checklist", db_path)
        _print_json(outline)

    elif args.command == "export":
        _ensure_case_exists(args.case_id, db_path)
        output = export_case(args.case_id, args.format, args.output or None, db_path)
        if not args.output:
            print(output)
        else:
            print(f"Export saved to {args.output}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
