import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEGAL_AGENT_SAFE_CHECK_DISABLED", "1")

from PySide6 import QtCore, QtWidgets

from legal_agent import db
from legal_agent.authority_validation import add_authority
from legal_agent.case_profile import build_case_profile
from legal_agent.case_tracks import LEGAL_TRACK_CHOICES, TRACK_FEDERAL_EDCA
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
