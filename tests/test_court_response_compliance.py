import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEGAL_AGENT_SAFE_CHECK_DISABLED", "1")

from PySide6 import QtWidgets

from legal_agent import db
from legal_agent.court_response_compliance import (
    NO_SAME_JURISDICTION_SUPPORT,
    STRICT_CERTAINTY_REJECTION,
    ReviewConfig,
    run_court_response_compliance_review,
    validate_courtlistener_result,
)
from legal_agent.intake import create_case, list_cases
from legal_agent_gui.main_window import MainWindow


class FakeCourtListenerClient:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query, config, limit=8):
        self.queries.append((query, config, limit))
        return {
            "ok": True,
            "status": "ok",
            "message": f"Returned {len(self.results)} fake result(s).",
            "query": query,
            "results": self.results[:limit],
        }


def fake_openai_reviewer(document_text, config, extraction_metadata):
    return {
        "mode": "mock_openai",
        "document_type_detected": "Motion response",
        "court_response_purpose": "Responds to a motion response request.",
        "confidence_score": 0.84,
        "issues": [
            {
                "section": "Unsupported Assertions",
                "severity": "Medium",
                "issue_title": "AI detected unsupported assertion",
                "location_in_document": "Argument section",
                "why_it_matters": "The assertion should be tied to evidence or authority.",
                "possible_consequence": "The court may disregard the assertion.",
                "recommended_correction": "Add an exhibit, declaration, or validated same-jurisdiction source.",
                "confidence_score": 0.79,
                "attorney_review_strongly_recommended": True,
            }
        ],
    }


def perfect_openai_reviewer(document_text, config, extraction_metadata):
    return {
        "mode": "mock_openai",
        "document_type_detected": "Motion response",
        "court_response_purpose": "Responds to a motion response request.",
        "confidence_score": 1.0,
        "issues": [],
    }


def fake_document_generator(document_text, config, strict_gate, issues, usable_sources):
    return {
        "summary": "Mock corrected response draft generated.",
        "content_markdown": (
            "# Corrected Response Draft\n\n"
            "This corrected draft answers the configured request and preserves objections.\n\n"
            "## Signature\n\n/s/ Test User\n\n"
            "## Proof of Service\n\nI served all required parties."
        ),
        "references_used": usable_sources,
    }


def review_config(**overrides):
    values = {
        "state": "California",
        "city": "Sacramento",
        "county": "Sacramento",
        "court_level": "Superior",
        "court_name": "Sacramento Superior Court",
        "judge_name": "Judge Rivera",
        "attorney_or_requesting_party_name": "Morgan Counsel",
        "request_type": "Motion response",
        "filing_or_response_deadline": "2026-06-01",
        "procedural_posture": "Opposition due before hearing.",
        "user_notes": "Judge asked for a narrow response to the motion.",
    }
    values.update(overrides)
    return ReviewConfig(**values)


def write_review_document(directory, content=None):
    path = Path(directory) / "response.txt"
    path.write_text(
        content
        or (
            "Response to motion.\n"
            "This is clearly true and the party will pay if the court asks.\n"
            "See Exhibit A.\n"
        ),
        encoding="utf-8",
    )
    return path


def write_complete_review_document(directory):
    path = Path(directory) / "complete_response.txt"
    path.write_text(
        (
            "Superior Court of California, County of Sacramento\n"
            "Sacramento Superior Court\n"
            "Judge Rivera\n"
            "Case No. 2026-CV-001\n"
            "Response to Motion Response Request from Morgan Counsel\n\n"
            "This response to motion is submitted before the 2026-06-01 deadline. "
            "The responding party addresses each requested point and preserves all objections. "
            "Factual statements are supported by the attached as Exhibit A declaration and record materials. "
            "The response is limited to the Sacramento Superior Court request and does not rely on any other venue. "
            "This paragraph adds sufficient body text for extraction review and confirms that each court request is answered directly. "
            "The filing party asks the court to accept this corrected response after human legal review.\n\n"
            "Dated: 2026-05-16\n"
            "Respectfully submitted,\n"
            "/s/ Test User\n"
            "Test User\n\n"
            "Proof of Service\n"
            "I served this response on Morgan Counsel by the required service method."
        ),
        encoding="utf-8",
    )
    return path


class CourtResponseComplianceTests(unittest.TestCase):
    def test_review_cannot_begin_without_required_jurisdiction_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_review_document(temp_dir)
            with self.assertRaises(ValueError) as context:
                run_court_response_compliance_review(
                    document,
                    review_config(state="", city="", court_level="", request_type=""),
                    storage_root=Path(temp_dir) / "reviews",
                    openai_reviewer=fake_openai_reviewer,
                    document_generator=fake_document_generator,
                )

        self.assertIn("state", str(context.exception))
        self.assertIn("city", str(context.exception))
        self.assertIn("court level", str(context.exception))
        self.assertIn("request type", str(context.exception))

    def test_missing_courtlistener_api_key_does_not_crash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_review_document(temp_dir)
            with patch.dict(os.environ, {}, clear=True):
                result = run_court_response_compliance_review(
                    document,
                    review_config(),
                    storage_root=Path(temp_dir) / "reviews",
                    openai_reviewer=fake_openai_reviewer,
                    document_generator=fake_document_generator,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["report"]["Review Summary"]["courtlistener_status"], "unavailable")
        self.assertIn("unavailable", result["report"]["CourtListener Same-Jurisdiction Findings"]["status"])

    def test_courtlistener_result_from_another_state_is_rejected(self):
        validation = validate_courtlistener_result(
            {
                "title": "Nevada motion response case",
                "court": "Nevada Supreme Court",
                "snippet": "motion response procedure",
            },
            review_config(),
        )

        self.assertFalse(validation["usable"])
        self.assertIn("does not match selected state", validation["reason"])

    def test_courtlistener_result_from_unrelated_city_or_county_is_rejected(self):
        validation = validate_courtlistener_result(
            {
                "title": "Los Angeles motion response case",
                "court": "Los Angeles County Superior Court, California",
                "snippet": "motion response procedure",
            },
            review_config(),
        )

        self.assertFalse(validation["usable"])
        self.assertIn("city/county", validation["reason"])

    def test_federal_authority_is_not_used_for_state_or_local_review(self):
        validation = validate_courtlistener_result(
            {
                "title": "Federal motion response case",
                "court": "United States District Court for the Eastern District of California",
                "snippet": "motion response procedure",
            },
            review_config(court_level="Superior"),
        )

        self.assertFalse(validation["usable"])
        self.assertIn("Federal authority cannot support", validation["reason"])

    def test_state_or_local_authority_is_not_used_for_federal_review(self):
        validation = validate_courtlistener_result(
            {
                "title": "California motion response case",
                "court": "California Supreme Court",
                "snippet": "motion response procedure",
            },
            review_config(court_level="Federal district court"),
        )

        self.assertFalse(validation["usable"])
        self.assertIn("State or local authority cannot support", validation["reason"])

    def test_same_jurisdiction_sources_are_allowed(self):
        validation = validate_courtlistener_result(
            {
                "title": "Sacramento motion response case",
                "court": "Sacramento County Superior Court, California",
                "date": "2022-01-05",
                "absolute_url": "https://www.courtlistener.com/opinion/1/example/",
                "snippet": "motion response procedure",
            },
            review_config(),
        )

        self.assertTrue(validation["usable"])

    def test_rejected_sources_are_logged_and_valid_sources_are_used(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "reviews"
            document = write_review_document(temp_dir)
            client = FakeCourtListenerClient(
                [
                    {
                        "title": "Sacramento motion response case",
                        "court": "Sacramento County Superior Court, California",
                        "date": "2022-01-05",
                        "absolute_url": "https://www.courtlistener.com/opinion/1/example/",
                        "snippet": "motion response procedure",
                    },
                    {
                        "title": "Nevada motion response case",
                        "court": "Nevada Supreme Court",
                        "date": "2021-01-05",
                        "absolute_url": "https://www.courtlistener.com/opinion/2/example/",
                        "snippet": "motion response procedure",
                    },
                ]
            )
            result = run_court_response_compliance_review(
                document,
                review_config(),
                storage_root=storage,
                openai_reviewer=fake_openai_reviewer,
                document_generator=fake_document_generator,
                courtlistener_client=client,
                now=datetime(2026, 5, 16, tzinfo=timezone.utc),
            )

            rejected_log = storage / "rejected_sources.jsonl"
            query_log = storage / "courtlistener_queries.jsonl"

            self.assertTrue(rejected_log.exists())
            self.assertTrue(query_log.exists())
            rejected_lines = rejected_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rejected_lines), 1)
            self.assertIn("Nevada", rejected_lines[0])
            self.assertEqual(len(result["report"]["CourtListener Same-Jurisdiction Findings"]), 1)
            self.assertNotIn(
                NO_SAME_JURISDICTION_SUPPORT,
                result["report"]["All Issues"][0]["supporting_local_rule_or_same_jurisdiction_source"],
            )

    def test_extracted_document_issues_are_included_in_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_review_document(temp_dir)
            result = run_court_response_compliance_review(
                document,
                review_config(),
                storage_root=Path(temp_dir) / "reviews",
                openai_reviewer=fake_openai_reviewer,
                document_generator=fake_document_generator,
            )

        titles = {issue["issue_title"] for issue in result["report"]["All Issues"]}
        self.assertIn("Signature block appears missing", titles)
        self.assertIn("AI detected unsupported assertion", titles)

    def test_feature_does_not_create_or_modify_case_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cases.db"
            db.init_db(db_path)
            create_case("Existing Case", db_path=str(db_path))
            before = [case.to_dict() for case in list_cases(str(db_path))]
            document = write_review_document(temp_dir)
            run_court_response_compliance_review(
                document,
                review_config(),
                storage_root=Path(temp_dir) / "reviews",
                openai_reviewer=fake_openai_reviewer,
                document_generator=fake_document_generator,
            )
            after = [case.to_dict() for case in list_cases(str(db_path))]

        self.assertEqual(before, after)

    def test_original_document_is_preserved_and_notes_are_included(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_review_document(temp_dir)
            result = run_court_response_compliance_review(
                document,
                review_config(user_notes="Manual note: check local standing order."),
                storage_root=Path(temp_dir) / "reviews",
                openai_reviewer=fake_openai_reviewer,
                document_generator=fake_document_generator,
            )
            preserved = Path(result["report"]["storage"]["preserved_document_path"])
            self.assertTrue(preserved.exists())
            self.assertEqual(document.read_text(encoding="utf-8"), preserved.read_text(encoding="utf-8"))
            self.assertEqual(
                result["report"]["Court Request Context"]["User notes/context"],
                "Manual note: check local standing order.",
            )

    def test_export_creates_durable_report_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_review_document(temp_dir)
            result = run_court_response_compliance_review(
                document,
                review_config(),
                storage_root=Path(temp_dir) / "reviews",
                openai_reviewer=fake_openai_reviewer,
                document_generator=fake_document_generator,
            )
            for path in result["report_paths"].values():
                self.assertTrue(Path(path).exists())
                self.assertGreater(Path(path).stat().st_size, 20)
            for path in result["generated_document_paths"].values():
                self.assertTrue(Path(path).exists())
                self.assertGreater(Path(path).stat().st_size, 20)

    def test_strict_gate_rejects_non_100_confidence_even_with_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_complete_review_document(temp_dir)
            client = FakeCourtListenerClient(
                [
                    {
                        "title": "Sacramento motion response case",
                        "court": "Sacramento County Superior Court, California",
                        "date": "2022-01-05",
                        "absolute_url": "https://www.courtlistener.com/opinion/1/example/",
                        "snippet": "motion response procedure",
                    }
                ]
            )
            result = run_court_response_compliance_review(
                document,
                review_config(),
                storage_root=Path(temp_dir) / "reviews",
                openai_reviewer=fake_openai_reviewer,
                document_generator=fake_document_generator,
                courtlistener_client=client,
            )

        gate = result["report"]["Strict Confidence Gate"]
        self.assertFalse(gate["accepted"])
        self.assertIn("OpenAI analysis did not report 100% certainty.", gate["rejection_reasons"])
        self.assertEqual(result["generated_document"]["certification_status"], "rejected")
        self.assertIn(STRICT_CERTAINTY_REJECTION, result["generated_document"]["warning"])

    def test_strict_gate_rejects_missing_same_jurisdiction_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_complete_review_document(temp_dir)
            with patch.dict(os.environ, {}, clear=True):
                result = run_court_response_compliance_review(
                    document,
                    review_config(),
                    storage_root=Path(temp_dir) / "reviews",
                    openai_reviewer=perfect_openai_reviewer,
                    document_generator=fake_document_generator,
                )

        gate = result["report"]["Strict Confidence Gate"]
        self.assertFalse(gate["accepted"])
        self.assertIn("No validated same-jurisdiction CourtListener reference is available.", gate["rejection_reasons"])

    def test_strict_gate_accepts_only_with_100_confidence_and_valid_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = write_complete_review_document(temp_dir)
            client = FakeCourtListenerClient(
                [
                    {
                        "title": "Sacramento motion response case",
                        "court": "Sacramento County Superior Court, California",
                        "date": "2022-01-05",
                        "absolute_url": "https://www.courtlistener.com/opinion/1/example/",
                        "snippet": "motion response procedure",
                    }
                ]
            )
            result = run_court_response_compliance_review(
                document,
                review_config(),
                storage_root=Path(temp_dir) / "reviews",
                openai_reviewer=perfect_openai_reviewer,
                document_generator=fake_document_generator,
                courtlistener_client=client,
            )

        gate = result["report"]["Strict Confidence Gate"]
        self.assertTrue(gate["accepted"])
        self.assertEqual(gate["usable_reference_count"], 1)
        self.assertEqual(result["generated_document"]["certification_status"], "accepted")

    def test_main_window_has_smart_document_review_top_tab(self):
        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "gui.db"
            window = MainWindow(db_path=str(db_path))

            self.assertEqual(window.workspace_tabs.tabText(1), "Smart Document Review")
            window.workspace_tabs.setCurrentIndex(1)

            self.assertEqual(window.stack.currentWidget(), window.views["Smart Document Review"])
            self.assertFalse(window.toolbar_widget.isVisible())
            self.assertFalse(window.sidebar.isEnabled())


if __name__ == "__main__":
    unittest.main()
