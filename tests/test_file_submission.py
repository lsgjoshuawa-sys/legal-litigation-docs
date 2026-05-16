import tempfile
import unittest
from pathlib import Path

from legal_agent import db
from legal_agent.authority_validation import list_authorities
from legal_agent.drafting import get_document
from legal_agent.file_submission import (
    HANDLER_ACTION,
    HANDLER_AUTHORITY,
    HANDLER_DRAFT,
    HANDLER_EVIDENCE,
    HANDLER_FACTS,
    HANDLER_RESEARCH,
    data_extraction_recommendation,
    infer_document_topic,
    is_data_extraction_compatible,
    read_file_preview,
    submit_file_to_handler,
)
from legal_agent.intake import create_case, list_action_items, list_evidence, list_facts
from legal_agent.research import get_research_logs


class FileSubmissionTest(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
        self.case_id = create_case("Submission Test", db_path=self.temp_db.name)

    def tearDown(self):
        Path(self.temp_db.name).unlink(missing_ok=True)

    def test_infers_authority_from_case_citation_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "research_case_note.txt"
            path.write_text("Smith v. Jones, 123 Cal.App.4th 456 discusses the holding.", encoding="utf-8")

            preview = read_file_preview(path)
            suggestion = infer_document_topic(path, preview)

        self.assertEqual(suggestion.handler, HANDLER_AUTHORITY)
        self.assertIn(suggestion.confidence, {"medium", "high"})

    def test_submits_file_to_evidence_handler(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "receipt.txt"
            path.write_text(
                "Title: Filing Fee Receipt\n"
                "Evidence type: receipt\n"
                "Description: Receipt for filing fee.\n",
                encoding="utf-8",
            )

            result = submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_EVIDENCE,
                preview_text=read_file_preview(path),
                extract_data=True,
                db_path=self.temp_db.name,
            )

        evidence = list_evidence(self.case_id, self.temp_db.name)
        self.assertEqual(result.handler, HANDLER_EVIDENCE)
        self.assertEqual(evidence[0]["title"], "Filing Fee Receipt")
        self.assertEqual(evidence[0]["evidence_type"], "receipt")
        self.assertIn("Receipt for filing fee.", evidence[0]["description"])

    def test_submits_file_to_authority_handler(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "case_authority.txt"
            path.write_text(
                "Title: Example v. City\n"
                "Authority type: case\n"
                "Citation: 10 F.3d 1\n",
                encoding="utf-8",
            )

            submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_AUTHORITY,
                preview_text=read_file_preview(path),
                extract_data=True,
                db_path=self.temp_db.name,
            )

        authorities = list_authorities(self.case_id, self.temp_db.name)
        self.assertEqual(authorities[0]["title"], "Example v. City")
        self.assertEqual(authorities[0]["authority_type"], "case")
        self.assertEqual(authorities[0]["citation"], "10 F.3d 1")
        self.assertEqual(authorities[0]["verified"], 0)

    def test_submits_file_to_research_handler_with_extracted_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "research_note.md"
            path.write_text(
                "Query: Can a filing deadline be extended?\n"
                "Source: CourtListener\n"
                "Result summary: Research suggests checking local rules.\n",
                encoding="utf-8",
            )

            submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_RESEARCH,
                preview_text=read_file_preview(path),
                extract_data=True,
                db_path=self.temp_db.name,
            )

        logs = get_research_logs(self.case_id, self.temp_db.name)
        self.assertEqual(logs[0]["query"], "Can a filing deadline be extended?")
        self.assertEqual(logs[0]["source"], "CourtListener")
        self.assertIn("local rules", logs[0]["result_summary"])

    def test_submits_file_to_action_handler_with_extracted_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "deadline_task.txt"
            path.write_text(
                "Action: Serve discovery responses\n"
                "Category: discovery\n"
                "Due date: 2026-06-01\n"
                "Status: open\n",
                encoding="utf-8",
            )

            submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_ACTION,
                preview_text=read_file_preview(path),
                extract_data=True,
                db_path=self.temp_db.name,
            )

        actions = list_action_items(self.case_id, self.temp_db.name)
        self.assertEqual(actions[0]["action_text"], "Serve discovery responses")
        self.assertEqual(actions[0]["category"], "discovery")
        self.assertEqual(actions[0]["due_date"], "2026-06-01")

    def test_submits_file_to_facts_handler_with_extracted_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timeline_fact.txt"
            path.write_text(
                "Date: 2026-05-01\n"
                "Fact: Defendant received written notice.\n"
                "Relevance: notice element\n",
                encoding="utf-8",
            )

            submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_FACTS,
                preview_text=read_file_preview(path),
                extract_data=True,
                db_path=self.temp_db.name,
            )

        facts = list_facts(self.case_id, self.temp_db.name)
        self.assertEqual(facts[0]["date"], "2026-05-01")
        self.assertEqual(facts[0]["fact_text"], "Defendant received written notice.")
        self.assertEqual(facts[0]["relevance"], "notice element")

    def test_submits_file_to_draft_handler_with_extracted_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "complaint_draft.md"
            path.write_text(
                "Title: Draft Complaint\n"
                "Document type: complaint\n"
                "Content: Draft allegations for review.\n",
                encoding="utf-8",
            )

            result = submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_DRAFT,
                preview_text=read_file_preview(path),
                extract_data=True,
                db_path=self.temp_db.name,
            )

        document = get_document(result.record_id, self.temp_db.name)
        self.assertEqual(document["title"], "Draft Complaint")
        self.assertEqual(document["document_type"], "complaint")
        self.assertEqual(document["draft_markdown"], "Draft allegations for review.")

    def test_submits_pdf_to_draft_handler_without_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "motion_packet.pdf"
            path.write_bytes(b"%PDF-1.4\n% test fixture\n")

            result = submit_file_to_handler(
                self.case_id,
                path,
                HANDLER_DRAFT,
                title="Motion Packet",
                extract_data=True,
                db_path=self.temp_db.name,
            )

        document = get_document(result.record_id, self.temp_db.name)
        self.assertEqual(result.handler, HANDLER_DRAFT)
        self.assertEqual(document["title"], "Motion Packet")
        self.assertEqual(document["document_type"], "motion")
        self.assertIn("motion_packet.pdf", document["draft_markdown"])

    def test_recommends_only_compatible_types_for_data_extraction(self):
        self.assertTrue(is_data_extraction_compatible("submission.txt"))
        self.assertFalse(is_data_extraction_compatible("submission.pdf"))
        self.assertIn("TXT", data_extraction_recommendation("submission.pdf"))


if __name__ == "__main__":
    unittest.main()
