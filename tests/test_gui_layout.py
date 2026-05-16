import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEGAL_AGENT_SAFE_CHECK_DISABLED", "1")

from PySide6 import QtCore, QtWidgets

from legal_agent import db
from legal_agent.authority_validation import add_authority
from legal_agent.case_profile import build_case_profile
from legal_agent.case_tracks import LEGAL_TRACK_CHOICES, TRACK_FEDERAL_EDCA
from legal_agent.intake import add_claim, add_evidence, create_case, list_claims, list_evidence
from legal_agent.research import add_research_log
from legal_agent_gui.app import _is_noisy_qt_message, _linux_display_preflight_error
from legal_agent_gui.courtlistener_research_view import CourtListenerResearchView
from legal_agent_gui.main_window import MainWindow
from legal_agent_gui.styles import APP_STYLE


class TestGuiLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_main_window_fits_available_screen(self):
        window = MainWindow(db_path=self.temp_db.name)
        available = QtWidgets.QApplication.primaryScreen().availableGeometry()

        self.assertLessEqual(window.width(), available.width())
        self.assertLessEqual(window.height(), available.height())

    def test_file_submission_opens_and_selects_evidence_record(self):
        case_id = create_case("File Submit UI", db_path=self.temp_db.name)
        with tempfile.TemporaryDirectory() as temp_dir:
            submitted_file = Path(temp_dir) / "test_evidence.txt"
            submitted_file.write_text("Evidence text from file submission.", encoding="utf-8")

            window = MainWindow(db_path=self.temp_db.name)
            window.refresh_case_data(select_case_id=case_id)
            submit_view = window.views["File Submission"]
            submit_view.file_input.setText(str(submitted_file))
            submit_view.title_input.setText("Submitted Evidence")
            submit_view.route_input.setCurrentText("Evidence")
            submit_view.preview_input.setPlainText("Evidence text from file submission.")

            submit_view._submit_file()

            evidence_view = window.views["Evidence"]
            self.assertEqual(window.stack.currentWidget(), evidence_view)
            self.assertEqual(evidence_view.evidence_list.count(), 1)
            self.assertEqual(evidence_view.evidence_list.currentItem().text(), "Submitted Evidence (document)")
            self.assertEqual(evidence_view.title_input.text(), "Submitted Evidence")

    def test_file_submission_open_route_button_uses_dropdown_before_submit(self):
        case_id = create_case("File Submit Route Button", db_path=self.temp_db.name)
        with tempfile.TemporaryDirectory() as temp_dir:
            submitted_file = Path(temp_dir) / "motion_to_route.pdf"
            submitted_file.write_bytes(b"%PDF-1.4\n")

            window = MainWindow(db_path=self.temp_db.name)
            window.refresh_case_data(select_case_id=case_id)
            submit_view = window.views["File Submission"]
            submit_view.file_input.setText(str(submitted_file))

            submit_view._analyze_file()
            submit_view.route_input.setCurrentText("Draft Generator")
            submit_view._open_current_handler()

            self.assertEqual(window.stack.currentWidget(), window.views["Draft Generator"])
            self.assertEqual(submit_view.message_label.text(), "Opened Draft Generator.")

    def test_file_submission_submits_pdf_to_selected_draft_handler(self):
        case_id = create_case("File Submit PDF Draft", db_path=self.temp_db.name)
        with tempfile.TemporaryDirectory() as temp_dir:
            submitted_file = Path(temp_dir) / "motion_to_draft.pdf"
            submitted_file.write_bytes(b"%PDF-1.4\n% test fixture\n")

            window = MainWindow(db_path=self.temp_db.name)
            window.refresh_case_data(select_case_id=case_id)
            submit_view = window.views["File Submission"]
            submit_view.file_input.setText(str(submitted_file))
            submit_view.title_input.setText("Motion PDF")

            submit_view._analyze_file()
            submit_view.route_input.setCurrentText("Draft Generator")
            submit_view._submit_file()

            draft_view = window.views["Draft Generator"]
            self.assertEqual(window.stack.currentWidget(), draft_view)
            self.assertEqual(draft_view.document_type_input.text(), "motion")
            self.assertIn("motion_to_draft.pdf", draft_view.output.toPlainText())
            self.assertIn("Submitted 'motion_to_draft.pdf' to Draft Generator", submit_view.message_label.text())

    def test_file_submission_surfaces_each_routed_handler_record(self):
        case_id = create_case("File Submit Routes", db_path=self.temp_db.name)
        window = MainWindow(db_path=self.temp_db.name)
        window.refresh_case_data(select_case_id=case_id)
        submit_view = window.views["File Submission"]

        submissions = [
            (
                "Authority Validation",
                "authority.txt",
                "Title: Route Test v. City\nAuthority type: case\nCitation: 22 F.3d 1\n",
                lambda: self.assertIn("Route Test v. City", window.views["Authority Validation"].list_widget.currentItem().text()),
            ),
            (
                "Legal Research",
                "research.txt",
                "Query: What is the filing standard?\nSource: local rule memo\nResult summary: Check local rule timing.\n",
                lambda: self.assertEqual(window.views["Legal Research"].query_input.text(), "What is the filing standard?"),
            ),
            (
                "Action Items & Due Dates",
                "action.txt",
                "Action: Review filed proof of service\nDue date: 2026-06-02\nCategory: service\n",
                lambda: self.assertEqual(window.views["Action Items & Due Dates"].action_input.toPlainText(), "Review filed proof of service"),
            ),
            (
                "Facts",
                "fact.txt",
                "Date: 2026-05-03\nFact: Agency received the claim notice.\nRelevance: exhaustion\n",
                lambda: self.assertEqual(window.views["Facts"].fact_text_input.toPlainText(), "Agency received the claim notice."),
            ),
            (
                "Draft Generator",
                "draft.md",
                "Title: Imported Motion\nDocument type: motion\nContent: Imported motion text.\n",
                lambda: self.assertIn("Imported motion text.", window.views["Draft Generator"].output.toPlainText()),
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for handler, filename, content, assertion in submissions:
                submitted_file = Path(temp_dir) / filename
                submitted_file.write_text(content, encoding="utf-8")
                submit_view.file_input.setText(str(submitted_file))
                submit_view.title_input.clear()
                submit_view.notes_input.clear()
                submit_view.route_input.setCurrentText(handler)
                submit_view.preview_input.setPlainText(content)
                submit_view.extract_data_input.setChecked(True)

                submit_view._submit_file()

                self.assertEqual(window.stack.currentWidget(), window.views[handler])
                assertion()

    def test_structured_list_fields_use_plain_text_in_gui(self):
        case_id = create_case("Plain List UI", db_path=self.temp_db.name)
        add_claim(case_id, "Negligence", required_elements_json='["Duty", "Breach"]', db_path=self.temp_db.name)
        add_evidence(case_id, "Photo", supports_claims_json='["Negligence"]', db_path=self.temp_db.name)
        add_research_log(case_id, "Query", "Source", "Summary", '["1", "2"]', self.temp_db.name)

        window = MainWindow(db_path=self.temp_db.name)
        window.refresh_case_data(select_case_id=case_id)

        claims_view = window.views["Claims / Defenses"]
        claims_view.claim_list.setCurrentRow(0)
        self.assertEqual(claims_view.required_input.toPlainText(), "Duty\nBreach")
        self.assertIn("One required element per line", claims_view.required_input.placeholderText())
        claims_view.required_input.setPlainText("Duty\nBreach\nCausation")
        claims_view._save_claim()
        self.assertEqual(json.loads(list_claims(case_id, self.temp_db.name)[0]["required_elements_json"]), ["Duty", "Breach", "Causation"])

        evidence_view = window.views["Evidence"]
        evidence_view.evidence_list.setCurrentRow(0)
        self.assertEqual(evidence_view.supports_input.toPlainText(), "Negligence")
        self.assertIn("One supported claim", evidence_view.supports_input.placeholderText())
        evidence_view.supports_input.setPlainText("Negligence\nNegligent Entrustment")
        evidence_view._save_evidence()
        self.assertEqual(json.loads(list_evidence(case_id, self.temp_db.name)[0]["supports_claims_json"]), ["Negligence", "Negligent Entrustment"])

        research_view = window.views["Legal Research"]
        research_view.log_list.setCurrentRow(0)
        self.assertEqual(research_view.authority_ids_input.text(), "1, 2")
        self.assertIn("commas or spaces", research_view.authority_ids_input.placeholderText())

    def test_views_use_scroll_area_and_compact_editors(self):
        window = MainWindow(db_path=self.temp_db.name)
        case_view = window.views["Case Intake"]

        self.assertIsInstance(case_view.scroll_area, QtWidgets.QScrollArea)
        self.assertEqual(case_view.scroll_area.verticalScrollBarPolicy(), QtCore.Qt.ScrollBarAsNeeded)
        self.assertLessEqual(case_view.description_input.maximumHeight(), 180)

    def test_case_intake_uses_descriptive_procedure_track_choices(self):
        window = MainWindow(db_path=self.temp_db.name)
        case_view = window.views["Case Intake"]
        choices = [case_view.track_input.itemText(index) for index in range(case_view.track_input.count())]

        self.assertEqual(choices, LEGAL_TRACK_CHOICES)
        self.assertNotIn("A", choices)
        self.assertNotIn("B", choices)
        self.assertNotIn("C", choices)

        case_view.track_input.setCurrentText(TRACK_FEDERAL_EDCA)

        self.assertIn("FRCP", case_view.track_purpose_label.text())

    def test_global_dropdown_and_list_item_states_are_readable(self):
        required_selectors = [
            "QListWidget::item:hover",
            "QListWidget::item:selected",
            "QListWidget::item:disabled",
            "QListView::item:focus",
            "QComboBox QAbstractItemView::item:hover",
            "QComboBox QAbstractItemView::item:selected",
            "QComboBox QAbstractItemView::item:disabled",
            "QMenu::item:selected",
            "QMenu::item:disabled",
            "selection-background-color: #1565c0",
            "selection-color: #ffffff",
        ]
        for selector in required_selectors:
            self.assertIn(selector, APP_STYLE)

        list_widget = QtWidgets.QListWidget()
        list_widget.setStyleSheet(APP_STYLE)
        normal_item = QtWidgets.QListWidgetItem("Normal")
        disabled_item = QtWidgets.QListWidgetItem("Disabled")
        disabled_item.setFlags(disabled_item.flags() & ~QtCore.Qt.ItemIsEnabled)
        list_widget.addItem(normal_item)
        list_widget.addItem(disabled_item)
        list_widget.setCurrentItem(normal_item)

        combo = QtWidgets.QComboBox()
        combo.setStyleSheet(APP_STYLE)
        combo.addItems(["Normal", "Disabled"])
        combo.model().item(1).setEnabled(False)
        combo.setCurrentIndex(0)

        self.assertTrue(normal_item.flags() & QtCore.Qt.ItemIsEnabled)
        self.assertFalse(disabled_item.flags() & QtCore.Qt.ItemIsEnabled)
        self.assertEqual(list_widget.currentItem().text(), "Normal")
        self.assertFalse(combo.model().item(1).isEnabled())
        self.assertEqual(combo.currentText(), "Normal")

    def test_courtlistener_research_validates_optional_court_code(self):
        view = CourtListenerResearchView(db_path=self.temp_db.name)

        view.court_input.setText("23019(a)")
        court, extra_query, notice = view._court_filter_context()

        self.assertEqual(court, "")
        self.assertEqual(extra_query, "23019(a)")
        self.assertIn("Included it in the search terms", notice)
        self.assertEqual(view._combine_query_terms("street contest Sacramento", extra_query), "street contest Sacramento 23019(a)")

        view.court_input.setText("CA9")
        court, extra_query, notice = view._court_filter_context()

        self.assertEqual(court, "court_id:ca9")
        self.assertEqual(extra_query, "")
        self.assertEqual(notice, "")

        view.court_input.setText("caed, ca9")
        court, extra_query, notice = view._court_filter_context()

        self.assertEqual(court, "court_id:(caed OR ca9)")
        self.assertEqual(extra_query, "")
        self.assertEqual(notice, "")

    def test_courtlistener_research_builds_location_aware_query(self):
        view = CourtListenerResearchView(db_path=self.temp_db.name)

        view.query_input.setPlainText("minimal evidence for street racing citation")
        view.location_input.setText("Sacramento California")
        view.court_ids_input.setText("caed, ca9, cal")
        view.statute_input.setText("Cal. Veh. Code 23109(a)")
        view.required_terms_input.setText("driver rights, evidence")
        view.exclude_terms_input.setText("DUI")
        view.date_after_input.setText("2015-01-01")
        view.date_before_input.setText("2026-01-01")
        view.status_input.setCurrentText("Published / precedential")

        query, notice = view._build_structured_search_query()

        self.assertEqual(notice, "")
        self.assertIn("minimal evidence for street racing citation", query)
        self.assertIn("Sacramento California", query)
        self.assertIn("Cal. Veh. Code 23109(a)", query)
        self.assertIn('AND "driver rights"', query)
        self.assertIn("AND evidence", query)
        self.assertIn("-DUI", query)
        self.assertIn("court_id:(caed OR ca9 OR cal)", query)
        self.assertIn("status:published", query)
        self.assertIn("dateFiled:[2015-01-01 TO 2026-01-01]", query)

    def test_courtlistener_location_preset_populates_court_ids(self):
        view = CourtListenerResearchView(db_path=self.temp_db.name)

        view.location_preset_input.setCurrentText("Sacramento / Eastern District of California")

        self.assertEqual(view.location_input.text(), "Sacramento California")
        self.assertIn("caed", view.court_ids_input.text())
        self.assertIn("calctapp3d", view.court_ids_input.text())
        self.assertIn("court_id:", view.query_preview.toPlainText())

    def test_courtlistener_strict_filters_disable_semantic_mode(self):
        view = CourtListenerResearchView(db_path=self.temp_db.name)

        view.search_mode_input.setCurrentText("Semantic natural-language search")
        view.court_ids_input.setText("cal")

        query, notice = view._build_structured_search_query()

        self.assertIn("court_id:cal", query)
        self.assertIn("semantic mode will be disabled", notice)
        self.assertFalse(view._selected_semantic("o"))

    def test_courtlistener_search_no_results_response_is_visible(self):
        view = CourtListenerResearchView(db_path=self.temp_db.name)

        view._run_query(
            lambda connector: {
                "ok": True,
                "status": "no_results",
                "message": "CourtListener returned 0 result(s).",
                "endpoint": "/search/",
                "request_params": {"q": "street contest", "type": "o", "semantic": "true"},
                "results": [],
                "raw_count": 0,
            },
            "street contest",
        )

        self.assertEqual(view.result_list.count(), 1)
        summary = view.result_list.item(0).text()
        self.assertIn("Status: no_results", summary)
        self.assertIn("Endpoint: /search/", summary)
        self.assertIn("type=o", summary)
        self.assertIn("Try broadening", summary)

    def test_courtlistener_citation_no_citations_response_is_visible(self):
        view = CourtListenerResearchView(db_path=self.temp_db.name)

        view._run_query(
            lambda connector: {
                "ok": True,
                "status": "no_citations",
                "message": "CourtListener did not find legal citations in the submitted text.",
                "results": [],
                "raw_count": 0,
            },
            "street contest Sacramento driver rights",
        )

        self.assertEqual(view.result_list.count(), 1)
        summary = view.result_list.item(0).text()
        self.assertIn("Status: no_citations", summary)
        self.assertIn("Citation Lookup only validates formal legal citations", summary)

    def test_main_window_initializes_empty_database_file(self):
        empty_db = tempfile.NamedTemporaryFile(delete=False)
        empty_db.close()
        try:
            window = MainWindow(db_path=empty_db.name)
            self.assertEqual(window.case_selector.count(), 1)
            self.assertEqual(window.case_selector.itemText(0), "Select case")
        finally:
            os.unlink(empty_db.name)

    def test_qt_message_filter_only_matches_known_terminal_spam(self):
        self.assertTrue(_is_noisy_qt_message("QTextCursor::setPosition: Position '10' out of range"))
        self.assertTrue(_is_noisy_qt_message('AtSpiAdaptor::applicationInterface does not implement "GetApplicationBusAddress"'))
        self.assertFalse(_is_noisy_qt_message("QWidget: Cannot create a QWidget without QApplication"))

    def test_display_preflight_allows_offscreen_qt(self):
        with patch("sys.platform", "linux"), patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}, clear=True):
            self.assertIsNone(_linux_display_preflight_error())

    def test_display_preflight_reports_missing_linux_display(self):
        with patch("sys.platform", "linux"), patch.dict(os.environ, {}, clear=True):
            self.assertIn("No graphical display", _linux_display_preflight_error())

    def test_gui_module_main_invokes_launcher(self):
        from legal_agent import gui

        with patch.object(gui, "run_gui") as run_gui:
            gui.main()

        run_gui.assert_called_once_with()

    def test_incomplete_gui_saves_refresh_case_profile_and_ai_view(self):
        window = MainWindow(db_path=self.temp_db.name)

        case_view = window.views["Case Intake"]
        case_view._save_case()
        case_id = window.current_case_id

        self.assertEqual(case_id, 1)
        self.assertEqual(window.case_selector.currentData(), case_id)

        window.views["Parties"]._save_party()
        window.views["Facts"]._save_fact()
        window.views["Claims / Defenses"]._save_claim()
        window.views["Evidence"]._save_evidence()
        window.views["Action Items & Due Dates"]._save_action()
        window.views["Legal Research"]._save_log()
        window.views["Audit Log / Verification History"]._add_event()

        courtlistener_view = window.views["CourtListener Research"]
        result = {
            "title": "Saved CourtListener Item",
            "citation": "123 Cal. 456",
            "court": "California",
            "date": "2026-01-01",
            "snippet": "Short public metadata summary.",
            "source": "CourtListener",
        }
        item = QtWidgets.QListWidgetItem("Saved CourtListener Item")
        item.setData(QtCore.Qt.UserRole, result)
        courtlistener_view.result_list.addItem(item)
        courtlistener_view.result_list.setCurrentRow(0)
        courtlistener_view._save_selected()

        authority_id = add_authority(
            case_id,
            "case",
            "Treatment Test Authority",
            "123 Cal. 456",
            "California",
            "Court of Appeal",
            db_path=self.temp_db.name,
        )
        treatment_view = window.views["Citation Treatment Checker"]
        treatment_view.authority_id_input.setText(str(authority_id))
        treatment_view.status_input.setCurrentText("criticized")
        treatment_view._save_status()

        citation_status = {
            "source": "CourtListener",
            "status": "disabled",
            "checked": False,
            "message": "CourtListener connector is disabled.",
            "results": [],
        }
        with patch("legal_agent.drafting.validate_output_citations", return_value=citation_status):
            window.views["Draft Generator"]._generate_draft()

        profile = build_case_profile(case_id, self.temp_db.name)
        item_types = {profile_item["item_type"] for profile_item in profile["items"]}
        self.assertTrue(
            {
                "party",
                "fact",
                "claim_or_defense",
                "evidence",
                "action_item",
                "research_log",
                "unverified_authority",
                "audit_event",
                "document",
            }.issubset(item_types)
        )

        ai_view = window.views["AI Argument Analysis"]
        ai_view.refresh()
        profile_titles = [ai_view.profile_list.item(index).text() for index in range(ai_view.profile_list.count())]

        self.assertTrue(any("party: Unnamed Party" in title for title in profile_titles))
        self.assertTrue(any("evidence: Untitled Evidence" in title for title in profile_titles))
        self.assertGreater(ai_view.profile_list.count(), 0)


if __name__ == "__main__":
    unittest.main()
