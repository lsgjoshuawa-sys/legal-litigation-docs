from __future__ import annotations
import os
from typing import Any, Dict, Optional

from PySide6 import QtCore, QtWidgets

from .styles import APP_STYLE
from .widgets import BaseView
from .dashboard import DashboardView
from .case_intake_view import CaseIntakeView
from .file_submission_view import FileSubmissionView
from .case_folder_intake_view import CaseFolderIntakeView
from .parties_view import PartiesView
from .facts_view import FactsView
from .claims_view import ClaimsView
from .evidence_view import EvidenceView
from .action_items_view import ActionItemsView
from .timeline_view import TimelineView
from .jurisdiction_view import JurisdictionView
from .procedural_rules_view import ProceduralRulesView
from .research_view import ResearchView
from .courtlistener_research_view import CourtListenerResearchView
from .authority_validation_view import AuthorityValidationView
from .treatment_view import TreatmentView
from .element_checklist_view import ElementChecklistView
from .evidence_review_view import EvidenceReviewView
from .document_strategy_view import DocumentStrategyView
from .draft_generator_view import DraftGeneratorView
from .ai_analysis_view import AIAnalysisView
from .vulnerability_view import VulnerabilityView
from .filing_checklist_view import FilingChecklistView
from .export_view import ExportView
from .settings_view import SettingsView
from .audit_log_view import AuditLogView
from . import widgets
from legal_agent.intake import list_case_ids, list_cases, get_case
from legal_agent.case_folders import scan_all_case_folders
from legal_agent.logger import get_logger
from legal_agent.observability import performance_checkpoint
from legal_agent.db import check_db_health, init_db
from .session_safety import install_safe_check

logger = get_logger(__name__)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, db_path: str | None = None) -> None:
        try:
            with performance_checkpoint(
                "main_window_initialization",
                context={"db_path_supplied": bool(db_path)},
                slow_ms=2500,
            ):
                super().__init__()
                logger.debug("Initializing MainWindow")
                self.db_path: Optional[str] = db_path
                self.current_case_id: int | None = None
                self.cases = []
                self.safe_check = None

                init_db(db_path)

                # Check database health
                if not check_db_health(db_path):
                    logger.warning("Database health check failed, attempting to continue")

                self.startup_folder_scan_result = None
                try:
                    self.startup_folder_scan_result = scan_all_case_folders(db_path=self.db_path)
                    logger.debug("Startup case-folder scan completed: %s", self.startup_folder_scan_result.to_dict())
                except Exception as exc:
                    logger.warning("Startup case-folder scan failed: %s", exc)
                
                self.setWindowTitle("Litigation Expert AI System")
                # Auto-adjust window size to available screen dimensions
                screen = QtWidgets.QApplication.primaryScreen()
                available_geometry = screen.availableGeometry()
                # Use most of the available screen without extending under taskbars or docks.
                width = min(max(900, int(available_geometry.width() * 0.9)), available_geometry.width())
                height = min(max(620, int(available_geometry.height() * 0.9)), available_geometry.height())
                self.setMinimumSize(min(720, width), min(500, height))
                self.resize(width, height)
                # Center the window on the screen
                frame_geometry = self.frameGeometry()
                frame_geometry.moveCenter(available_geometry.center())
                self.move(frame_geometry.topLeft())
                self.setStyleSheet(APP_STYLE)
                self.central: QtWidgets.QWidget = QtWidgets.QWidget()
                self.setCentralWidget(self.central)
                self.main_layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout(self.central)
                self.main_layout.setContentsMargins(0, 0, 0, 0)
                self._build_sidebar()
                self._build_content()
                self.refresh_case_data()
                ready_message = "Ready"
                if self.startup_folder_scan_result:
                    if self.startup_folder_scan_result.warnings:
                        ready_message = "Ready - case-folder extraction pending: " + "; ".join(self.startup_folder_scan_result.warnings)
                    elif self.startup_folder_scan_result.pending_extractions:
                        ready_message = f"Ready - {self.startup_folder_scan_result.pending_extractions} file extractions pending"
                self.statusBar().showMessage(ready_message)
                if os.getenv("LEGAL_AGENT_SAFE_CHECK_DISABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
                    self.safe_check = install_safe_check(self, db_path)
                    if ready_message == "Ready":
                        self.statusBar().showMessage("Ready - safe check active")
                logger.debug("MainWindow initialization completed successfully")
        except Exception as e:
            logger.exception("Failed to initialize MainWindow")
            QtWidgets.QMessageBox.critical(None, "Initialization Error", 
                                          f"Failed to start application:\n{str(e)[:200]}")
            raise

    def _build_sidebar(self) -> None:
        self.sidebar = QtWidgets.QListWidget()
        self.sidebar.setMaximumWidth(260)
        self.sidebar.addItems([
            "Dashboard",
            "Case Intake",
            "File Submission",
            "Case Folder Intake",
            "Parties",
            "Facts",
            "Claims / Defenses",
            "Evidence",
            "Action Items & Due Dates",
            "Litigation Timeline",
            "Jurisdiction Classifier",
            "Procedural Rules",
            "Legal Research",
            "CourtListener Research",
            "Authority Validation",
            "Citation Treatment Checker",
            "Claim Element Checklist",
            "Evidence Sufficiency Review",
            "Document Strategy",
            "Draft Generator",
            "AI Argument Analysis",
            "Vulnerability / Demurrer-Proofing Review",
            "Filing Readiness Checklist",
            "Export Center",
            "Settings",
            "Audit Log / Verification History",
        ])
        self.sidebar.currentRowChanged.connect(self._switch_view)
        self.main_layout.addWidget(self.sidebar)

    def _build_content(self) -> None:
        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(18, 12, 18, 12)
        self.content_layout.setSpacing(10)
        self.toolbar_widget = QtWidgets.QWidget()
        self.toolbar_layout = QtWidgets.QHBoxLayout(self.toolbar_widget)
        self.toolbar_layout.setContentsMargins(8, 8, 8, 8)

        self.case_selector = QtWidgets.QComboBox()
        self.case_selector.currentIndexChanged.connect(self._refresh_current_case)
        self.toolbar_layout.addWidget(QtWidgets.QLabel("Active Case:"))
        self.toolbar_layout.addWidget(self.case_selector)
        self.refresh_button = QtWidgets.QPushButton("Refresh Case Data")
        self.refresh_button.clicked.connect(lambda: self.refresh_case_data())
        self.toolbar_layout.addWidget(self.refresh_button)
        self.toolbar_layout.addStretch(1)
        self.content_layout.addWidget(self.toolbar_widget)

        self.stack = QtWidgets.QStackedWidget()
        self.content_layout.addWidget(self.stack, 1)
        self.main_layout.addWidget(self.content_area)

        self.views: dict[str, BaseView] = {
            "Dashboard": DashboardView(self.db_path),
            "Case Intake": CaseIntakeView(self.db_path, self),
            "File Submission": FileSubmissionView(self.db_path),
            "Case Folder Intake": CaseFolderIntakeView(self.db_path),
            "Parties": PartiesView(self.db_path),
            "Facts": FactsView(self.db_path),
            "Claims / Defenses": ClaimsView(self.db_path),
            "Evidence": EvidenceView(self.db_path),
            "Action Items & Due Dates": ActionItemsView(self.db_path),
            "Litigation Timeline": TimelineView(self.db_path),
            "Jurisdiction Classifier": JurisdictionView(self.db_path),
            "Procedural Rules": ProceduralRulesView(self.db_path),
            "Legal Research": ResearchView(self.db_path),
            "CourtListener Research": CourtListenerResearchView(self.db_path),
            "Authority Validation": AuthorityValidationView(self.db_path),
            "Citation Treatment Checker": TreatmentView(self.db_path),
            "Claim Element Checklist": ElementChecklistView(self.db_path),
            "Evidence Sufficiency Review": EvidenceReviewView(self.db_path),
            "Document Strategy": DocumentStrategyView(self.db_path),
            "Draft Generator": DraftGeneratorView(self.db_path),
            "AI Argument Analysis": AIAnalysisView(self.db_path),
            "Vulnerability / Demurrer-Proofing Review": VulnerabilityView(self.db_path),
            "Filing Readiness Checklist": FilingChecklistView(self.db_path),
            "Export Center": ExportView(self.db_path),
            "Settings": SettingsView(self.db_path),
            "Audit Log / Verification History": AuditLogView(self.db_path),
        }
        for view in self.views.values():
            view.prepare_for_display()
            self.stack.addWidget(view)
        self.sidebar.setCurrentRow(0)

    def _load_cases(self, selected_case_id: int | None = None) -> None:
        self.case_selector.blockSignals(True)
        self.case_selector.clear()
        self.cases = list_cases(self.db_path)
        self.case_selector.addItem("Select case", None)
        selected_index = 0
        for case in self.cases:
            self.case_selector.addItem(f"{case.id} - {case.title}", case.id)
            if selected_case_id is not None and case.id == selected_case_id:
                selected_index = self.case_selector.count() - 1
        self.case_selector.setCurrentIndex(selected_index)
        self.case_selector.blockSignals(False)

    def refresh_case_data(self, select_case_id: int | None = None) -> None:
        with performance_checkpoint(
            "gui_refresh_case_data",
            context={"select_case_id": bool(select_case_id)},
            slow_ms=750,
        ):
            selected_case_id = select_case_id
            if selected_case_id is None:
                selected_case_id = self.case_selector.currentData() if hasattr(self, "case_selector") else self.current_case_id
            self._load_cases(selected_case_id)
            self._refresh_current_case(self.case_selector.currentIndex())

    def _refresh_current_case(self, index: int) -> None:
        with performance_checkpoint(
            "gui_refresh_current_case",
            context={"has_index": index >= 0, "view_count": len(getattr(self, "views", {}))},
            slow_ms=1000,
        ):
            case_id = self.case_selector.itemData(index) if index >= 0 else None
            self.current_case_id = case_id
            for view in self.views.values():
                if hasattr(view, "set_case_id"):
                    view.set_case_id(case_id)
                view.refresh()
            if case_id:
                case = get_case(case_id, self.db_path)
                description = case.description if case else ""
                self.statusBar().showMessage(f"Active case: {case_id} - {description}")
            else:
                self.statusBar().showMessage("No active case selected.")

    def _switch_view(self, index: int) -> None:
        with performance_checkpoint(
            "gui_switch_view",
            context={"index": index},
            slow_ms=500,
        ):
            self.stack.setCurrentIndex(index)
            current_view = self.stack.currentWidget()
            if hasattr(current_view, "refresh"):
                current_view.refresh()
            if self.safe_check:
                self.safe_check.schedule_snapshot()

    def closeEvent(self, event: QtCore.QCloseEvent) -> None:
        if self.safe_check:
            self.safe_check.shutdown()
        super().closeEvent(event)

    def run(self) -> None:
        self.show()
