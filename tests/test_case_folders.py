import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_agent import db
from legal_agent.case_folders import (
    SECTION_FOLDERS,
    SYSTEM_FOLDERS,
    calculate_sha256,
    case_directory,
    list_case_extractions,
    list_case_file_records,
    list_case_folder_errors,
    scan_case_folder,
)
from legal_agent.intake import add_evidence, create_case, list_evidence


class StaticExtractor:
    provider = "mock-test"
    model = "unit-test"

    def __init__(self, recommended_section: str = "05_evidence", fail: bool = False) -> None:
        self.recommended_section = recommended_section
        self.fail = fail
        self.calls = 0

    def extract(self, path, text, section_folder, section_label):
        self.calls += 1
        if self.fail:
            raise ValueError("mock extraction failure")
        return {
            "summary": f"Summary for {path.name}",
            "key_facts": ["Defendant received notice."],
            "parties_mentioned": ["Alice Smith", "Bob Jones"],
            "dates_and_deadlines": ["2026-06-01"],
            "evidence_references": ["Exhibit A"],
            "claims_or_defenses_mentioned": ["Negligence"],
            "jurisdiction_clues": ["California Superior Court"],
            "procedural_issues": ["service deadline"],
            "legal_authorities_cited": ["123 Cal.App.4th 456"],
            "action_items": ["Review Exhibit A"],
            "confidence_score": 0.88,
            "extraction_warnings": [],
            "recommended_destination_section": self.recommended_section,
        }


class CaseFolderIntakeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = str(self.root / "legal_agent.db")
        self.env_patch = patch.dict(
            os.environ,
            {
                "LEGAL_AGENT_CASES_DIR": str(self.root / "cases"),
                "OPENAI_API_KEY": "",
                "LEGAL_AGENT_INTAKE_MOCK_OPENAI": "false",
            },
        )
        self.env_patch.start()
        db.init_db(self.db_path)

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_case_folders_are_created_after_intake_save(self):
        case_id = create_case("Folder Test / Bad:Title?", db_path=self.db_path)

        folder = case_directory(case_id, "Folder Test / Bad:Title?", db_path=self.db_path, create=False)

        self.assertTrue(folder.exists())
        self.assertTrue(folder.name.startswith(f"{case_id}_Folder_Test_Bad_Title"))
        for section in SECTION_FOLDERS + SYSTEM_FOLDERS:
            self.assertTrue((folder / section).is_dir(), section)
        self.assertTrue((folder / "_manifest" / "files.jsonl").exists())
        self.assertTrue((folder / "_manifest" / "extractions.jsonl").exists())
        self.assertTrue((folder / "_manifest" / "errors.jsonl").exists())

    def test_files_dropped_into_section_folders_are_detected_hashed_and_extracted(self):
        case_id = create_case("Evidence Intake", db_path=self.db_path)
        folder = case_directory(case_id, "Evidence Intake", db_path=self.db_path)
        evidence_file = folder / "05_evidence" / "receipt.txt"
        evidence_file.write_text("Exhibit A\nFact: Defendant received notice on 2026-06-01.", encoding="utf-8")
        expected_hash = calculate_sha256(evidence_file)
        extractor = StaticExtractor()

        result = scan_case_folder(case_id, db_path=self.db_path, extractor=extractor)

        files = list_case_file_records(case_id, self.db_path)
        extractions = list_case_extractions(case_id, self.db_path, "05_evidence")
        self.assertEqual(result.extracted_files, 1)
        self.assertEqual(extractor.calls, 1)
        self.assertEqual(files[0]["sha256"], expected_hash)
        self.assertEqual(files[0]["case_id"], case_id)
        self.assertEqual(files[0]["section_folder"], "05_evidence")
        self.assertEqual(files[0]["filename"], "receipt.txt")
        self.assertEqual(files[0]["file_size"], evidence_file.stat().st_size)
        self.assertTrue(files[0]["chain_of_custody"]["original_preserved"])
        self.assertTrue(evidence_file.exists())
        self.assertEqual(extractions[0]["target_section_folder"], "05_evidence")
        self.assertEqual(extractions[0]["extraction"]["summary"], "Summary for receipt.txt")
        self.assertEqual(extractions[0]["confidence_score"], 0.88)

    def test_duplicate_hashes_are_recorded_but_not_extracted_twice(self):
        case_id = create_case("Duplicate Intake", db_path=self.db_path)
        folder = case_directory(case_id, "Duplicate Intake", db_path=self.db_path)
        first = folder / "03_facts" / "notice_a.txt"
        second = folder / "05_evidence" / "notice_b.txt"
        first.write_text("Same content for duplicate detection.", encoding="utf-8")
        second.write_text("Same content for duplicate detection.", encoding="utf-8")
        extractor = StaticExtractor(recommended_section="03_facts")

        result = scan_case_folder(case_id, db_path=self.db_path, extractor=extractor)

        files = list_case_file_records(case_id, self.db_path)
        extractions = list_case_extractions(case_id, self.db_path)
        duplicate_records = [record for record in files if record["status"] == "duplicate_skipped"]
        self.assertEqual(result.duplicate_files, 1)
        self.assertEqual(result.extracted_files, 1)
        self.assertEqual(extractor.calls, 1)
        self.assertEqual(len(files), 2)
        self.assertEqual(len(extractions), 1)
        self.assertEqual(len(duplicate_records), 1)
        self.assertTrue(duplicate_records[0]["duplicate_of"])

    def test_mocked_openai_extraction_failure_is_logged(self):
        case_id = create_case("Failure Intake", db_path=self.db_path)
        folder = case_directory(case_id, "Failure Intake", db_path=self.db_path)
        failed_file = folder / "05_evidence" / "bad.txt"
        failed_file.write_text("This file triggers a mocked failure.", encoding="utf-8")

        result = scan_case_folder(case_id, db_path=self.db_path, extractor=StaticExtractor(fail=True))

        files = list_case_file_records(case_id, self.db_path)
        errors = list_case_folder_errors(case_id, self.db_path)
        self.assertEqual(result.failed_files, 1)
        self.assertEqual(files[0]["status"], "failed")
        self.assertTrue(failed_file.exists())
        self.assertEqual(errors[0]["error_type"], "extraction_failed")
        self.assertIn("mock extraction failure", errors[0]["message"])

    def test_missing_api_key_marks_text_files_pending_without_crashing(self):
        case_id = create_case("Pending Intake", db_path=self.db_path)
        folder = case_directory(case_id, "Pending Intake", db_path=self.db_path)
        pending_file = folder / "03_facts" / "fact_note.txt"
        pending_file.write_text("Fact: No API key should be needed to index this.", encoding="utf-8")

        result = scan_case_folder(case_id, db_path=self.db_path)

        files = list_case_file_records(case_id, self.db_path)
        extractions = list_case_extractions(case_id, self.db_path)
        self.assertEqual(result.pending_extractions, 1)
        self.assertEqual(files[0]["status"], "pending_extraction")
        self.assertEqual(extractions[0]["status"], "pending_extraction")
        self.assertIn("OPENAI_API_KEY", extractions[0]["reason"])

    def test_environment_mock_mode_extracts_without_real_openai_key(self):
        case_id = create_case("Environment Mock Intake", db_path=self.db_path)
        folder = case_directory(case_id, "Environment Mock Intake", db_path=self.db_path)
        mock_file = folder / "05_evidence" / "mock_note.txt"
        mock_file.write_text("Exhibit A has a deadline of 2026-06-01.", encoding="utf-8")

        with patch.dict(os.environ, {"LEGAL_AGENT_INTAKE_MOCK_OPENAI": "true", "OPENAI_API_KEY": ""}):
            result = scan_case_folder(case_id, db_path=self.db_path)

        extractions = list_case_extractions(case_id, self.db_path)
        self.assertEqual(result.extracted_files, 1)
        self.assertEqual(extractions[0]["ai_provider"], "mock")
        self.assertEqual(extractions[0]["status"], "extracted")

    def test_manual_user_data_is_not_overwritten_by_ai_extraction(self):
        case_id = create_case("Manual Separation", db_path=self.db_path)
        evidence_id = add_evidence(
            case_id,
            "Manual Evidence",
            "document",
            "User-entered description stays intact.",
            db_path=self.db_path,
        )
        folder = case_directory(case_id, "Manual Separation", db_path=self.db_path)
        ai_file = folder / "05_evidence" / "ai_note.txt"
        ai_file.write_text("Exhibit A says something different.", encoding="utf-8")

        scan_case_folder(case_id, db_path=self.db_path, extractor=StaticExtractor())

        manual_evidence = list_evidence(case_id, self.db_path)
        extractions = list_case_extractions(case_id, self.db_path, "05_evidence")
        self.assertEqual(len(manual_evidence), 1)
        self.assertEqual(manual_evidence[0]["id"], evidence_id)
        self.assertEqual(manual_evidence[0]["title"], "Manual Evidence")
        self.assertEqual(manual_evidence[0]["description"], "User-entered description stays intact.")
        self.assertEqual(len(extractions), 1)
        self.assertEqual(extractions[0]["target_section_folder"], "05_evidence")

    def test_wrong_folder_recommendation_is_logged_without_moving_original(self):
        case_id = create_case("Recommendation Intake", db_path=self.db_path)
        folder = case_directory(case_id, "Recommendation Intake", db_path=self.db_path)
        misplaced = folder / "05_evidence" / "deadline.txt"
        misplaced.write_text("Deadline: file opposition by 2026-06-01.", encoding="utf-8")

        scan_case_folder(
            case_id,
            db_path=self.db_path,
            extractor=StaticExtractor(recommended_section="06_action_items_due_dates"),
        )

        extractions = list_case_extractions(case_id, self.db_path)
        errors = list_case_folder_errors(case_id, self.db_path)
        self.assertTrue(misplaced.exists())
        self.assertEqual(extractions[0]["target_section_folder"], "05_evidence")
        self.assertEqual(extractions[0]["recommended_destination_section"], "06_action_items_due_dates")
        self.assertEqual(errors[0]["error_type"], "section_recommendation")
        self.assertTrue(errors[0]["details"]["original_preserved"])


if __name__ == "__main__":
    unittest.main()
