from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from legal_agent.court_response_compliance import (
    COURT_LEVEL_CHOICES,
    DISCLAIMER,
    FEATURE_NAME,
    REQUEST_TYPE_CHOICES,
    collect_review_documents_from_case_folder,
    create_smart_review_case_folder,
    list_smart_review_case_folders,
    report_to_markdown,
    run_court_response_compliance_review,
    run_court_response_compliance_review_from_case_folder,
    smart_review_cases_root,
)
from legal_agent.logger import get_logger
from .widgets import BaseView

logger = get_logger("legal_agent.gui.court_response_compliance")


class CourtResponseComplianceView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(
            FEATURE_NAME,
            "Review a legal response document before filing without attaching it to a saved case record.",
        )
        self.db_path = db_path
        self.last_result: dict[str, Any] | None = None
        self.project_root = Path.cwd()
        self.selected_case_folder: Path | None = None

        self._use_vertical_scroll_only()

        self.cases_root_label = QtWidgets.QLabel(f"Case folder root: {smart_review_cases_root(self.project_root)}")
        self.cases_root_label.setWordWrap(True)
        self.layout.addWidget(self.cases_root_label)

        self.case_folder_name_input = QtWidgets.QLineEdit()
        self.case_folder_name_input.setPlaceholderText("Case name for a Smart Document Review folder")
        self.create_case_folder_button = QtWidgets.QPushButton("Create Case Folder")
        self.refresh_case_folders_button = QtWidgets.QPushButton("Refresh Folders")
        self.create_case_folder_button.clicked.connect(self._create_case_folder)
        self.refresh_case_folders_button.clicked.connect(self._refresh_case_folders)

        case_create_row = QtWidgets.QHBoxLayout()
        case_create_row.addWidget(self.case_folder_name_input, 1)
        case_create_row.addWidget(self.create_case_folder_button)
        case_create_row.addWidget(self.refresh_case_folders_button)
        self.layout.addLayout(case_create_row)

        self.case_folder_list = QtWidgets.QListWidget()
        self.case_folder_list.setMaximumHeight(120)
        self.case_folder_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.case_folder_list.currentItemChanged.connect(lambda _current, _previous: self._load_selected_case_folder())
        self.layout.addWidget(self.case_folder_list)

        self.load_case_folder_button = QtWidgets.QPushButton("Load Selected Folder")
        self.open_case_folder_button = QtWidgets.QPushButton("Open Selected Folder")
        self.run_case_folder_button = QtWidgets.QPushButton("Run Selected Folder Review")
        self.load_case_folder_button.clicked.connect(self._load_selected_case_folder)
        self.open_case_folder_button.clicked.connect(self._open_selected_case_folder)
        self.run_case_folder_button.clicked.connect(self._run_selected_case_folder_review)
        folder_action_grid = QtWidgets.QGridLayout()
        for index, button in enumerate(
            [self.load_case_folder_button, self.open_case_folder_button, self.run_case_folder_button]
        ):
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            folder_action_grid.addWidget(button, 0, index)
        self.layout.addLayout(folder_action_grid)

        self.file_input = QtWidgets.QTextEdit()
        self.file_input.setPlaceholderText("Select one or more source files. Each path appears on its own line and will be combined into one generated draft.")
        self.file_input.setMaximumHeight(90)
        self._wrap_text_edit(self.file_input)
        self.browse_button = QtWidgets.QPushButton("Browse Files")
        self.browse_button.clicked.connect(self._browse_document)
        file_row = QtWidgets.QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.addWidget(self.file_input, 1)
        file_row.addWidget(self.browse_button)

        self.state_input = QtWidgets.QLineEdit()
        self.state_input.setPlaceholderText("State where the court is located")
        self.city_input = QtWidgets.QLineEdit()
        self.city_input.setPlaceholderText("City where the court is located")
        self.county_input = QtWidgets.QLineEdit()
        self.county_input.setPlaceholderText("County, if known")

        self.court_level_input = QtWidgets.QComboBox()
        self.court_level_input.addItem("")
        self.court_level_input.addItems(COURT_LEVEL_CHOICES)
        self.court_name_input = QtWidgets.QLineEdit()
        self.court_name_input.setPlaceholderText("Court name, if known")
        self.judge_name_input = QtWidgets.QLineEdit()
        self.judge_name_input.setPlaceholderText("Judge name, if known")
        self.requesting_party_input = QtWidgets.QLineEdit()
        self.requesting_party_input.setPlaceholderText("Attorney or requesting party name, if applicable")

        self.request_type_input = QtWidgets.QComboBox()
        self.request_type_input.addItem("")
        self.request_type_input.addItems(REQUEST_TYPE_CHOICES)
        self.deadline_input = QtWidgets.QLineEdit()
        self.deadline_input.setPlaceholderText("Filing or response deadline, if known")
        self.posture_input = QtWidgets.QTextEdit()
        self.posture_input.setPlaceholderText("Procedural posture, if known")
        self._wrap_text_edit(self.posture_input)
        self.notes_input = QtWidgets.QTextEdit()
        self.notes_input.setPlaceholderText("User notes, court request context, filing instructions, or known concerns")
        self._wrap_text_edit(self.notes_input)

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        form.addRow("Files to combine/review:", file_row)
        form.addRow("State:", self.state_input)
        form.addRow("City:", self.city_input)
        form.addRow("County:", self.county_input)
        form.addRow("Court level:", self.court_level_input)
        form.addRow("Court name:", self.court_name_input)
        form.addRow("Judge name:", self.judge_name_input)
        form.addRow("Attorney/requesting party:", self.requesting_party_input)
        form.addRow("Request type:", self.request_type_input)
        form.addRow("Deadline:", self.deadline_input)
        form.addRow("Procedural posture:", self.posture_input)
        form.addRow("Notes/context:", self.notes_input)
        self.layout.addLayout(form)

        self.review_button = QtWidgets.QPushButton("Run Compliance Review")
        self.export_json_button = QtWidgets.QPushButton("Export JSON")
        self.export_markdown_button = QtWidgets.QPushButton("Export Markdown")
        self.export_pdf_button = QtWidgets.QPushButton("Export PDF")
        self.generated_markdown_button = QtWidgets.QPushButton("Draft Markdown")
        self.generated_pdf_button = QtWidgets.QPushButton("Draft PDF")
        self.review_button.clicked.connect(self._run_review)
        self.export_json_button.clicked.connect(lambda: self._export_existing_report("json"))
        self.export_markdown_button.clicked.connect(lambda: self._export_existing_report("markdown"))
        self.export_pdf_button.clicked.connect(lambda: self._export_existing_report("pdf"))
        self.generated_markdown_button.clicked.connect(lambda: self._export_generated_document("markdown"))
        self.generated_pdf_button.clicked.connect(lambda: self._export_generated_document("pdf"))

        review_row = QtWidgets.QHBoxLayout()
        review_row.addWidget(self.review_button)
        review_row.addStretch(1)
        self.layout.addLayout(review_row)

        export_grid = QtWidgets.QGridLayout()
        export_grid.setHorizontalSpacing(8)
        export_grid.setVerticalSpacing(8)
        for index, button in enumerate(
            [
                self.export_json_button,
                self.export_markdown_button,
                self.export_pdf_button,
                self.generated_markdown_button,
                self.generated_pdf_button,
            ]
        ):
            row = index // 3
            column = index % 3
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            export_grid.addWidget(button, row, column)
        self.layout.addLayout(export_grid)

        self.status_label = QtWidgets.QLabel(DISCLAIMER)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.status_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.layout.addWidget(self.status_label)

        self.combine_label = QtWidgets.QLabel(
            "Document generation will combine all selected source files; they are combined into one proposed corrected response draft."
        )
        self.combine_label.setWordWrap(True)
        self.layout.addWidget(self.combine_label)

        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(360)
        self._wrap_text_edit(self.output)
        self.layout.addWidget(self.output)
        self._set_export_buttons_enabled(False)
        self._refresh_case_folders()

    def refresh(self) -> None:
        self._set_export_buttons_enabled(bool(self.last_result))
        self._refresh_case_folders()

    def _browse_document(self) -> None:
        try:
            file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self,
                "Select document(s) for court response compliance review",
                str(Path.home()),
                "Documents (*.pdf *.docx *.txt *.md *.rtf *.html *.htm *.json *.xml *.csv);;All files (*.*)",
            )
            if file_paths:
                self.file_input.setPlainText("\n".join(file_paths))
                self.status_label.setText(
                    f"{len(file_paths)} source file(s) selected. The generated draft will combine them into one document."
                )
        except Exception as exc:
            self._show_error("Browse document", exc)

    def _run_review(self) -> None:
        self.output.clear()
        self.status_label.setText("Running standalone court response compliance review...")
        QtWidgets.QApplication.processEvents()
        try:
            result = run_court_response_compliance_review(
                self.file_input.toPlainText().strip(),
                self._config_from_inputs(),
            )
        except Exception as exc:
            self.last_result = None
            self._set_export_buttons_enabled(False)
            self._show_error("Court response compliance review", exc)
            return

        self.last_result = result
        report = result.get("report", {})
        self.output.setPlainText(report_to_markdown(report))
        paths = result.get("report_paths", {})
        generated_paths = result.get("generated_document_paths", {})
        gate = report.get("Strict Confidence Gate", {})
        self.status_label.setText(
            "Review complete.\n"
            f"Strict gate accepted: {gate.get('accepted', False)}\n"
            f"Source documents combined: {report.get('Generated Corrected Document', {}).get('combined_source_document_count', 1)}\n"
            f"Report JSON: {paths.get('json', 'unavailable')}\n"
            f"Generated draft Markdown: {generated_paths.get('markdown', 'unavailable')}"
        )
        self._set_export_buttons_enabled(True)

    def _run_selected_case_folder_review(self) -> None:
        case_folder = self._selected_case_folder_path()
        if not case_folder:
            self.status_label.setText("Select a Smart Document Review case folder first.")
            return
        self.output.clear()
        self.status_label.setText("Running fresh folder-limited Smart Document Review...")
        QtWidgets.QApplication.processEvents()
        try:
            result = run_court_response_compliance_review_from_case_folder(
                case_folder,
                self._config_from_inputs(),
                project_root=self.project_root,
            )
        except Exception as exc:
            self.last_result = None
            self._set_export_buttons_enabled(False)
            self._show_error("Selected folder review", exc)
            return

        self.last_result = result
        report = result.get("report", {})
        self.output.setPlainText(report_to_markdown(report))
        paths = result.get("report_paths", {})
        generated_paths = result.get("generated_document_paths", {})
        gate = report.get("Strict Confidence Gate", {})
        scope = report.get("Extraction Metadata", {}).get("source_scope", {})
        self.status_label.setText(
            "Folder review complete.\n"
            f"Case folder: {scope.get('case_folder', case_folder)}\n"
            f"Freshly scanned files: {scope.get('selected_file_count', 0)}\n"
            f"Strict gate accepted: {gate.get('accepted', False)}\n"
            f"Report JSON: {paths.get('json', 'unavailable')}\n"
            f"Generated draft Markdown: {generated_paths.get('markdown', 'unavailable')}"
        )
        self._set_export_buttons_enabled(True)

    def _create_case_folder(self) -> None:
        try:
            result = create_smart_review_case_folder(self.case_folder_name_input.text(), self.project_root)
        except Exception as exc:
            self._show_error("Create Smart Document Review case folder", exc)
            return
        self.case_folder_name_input.clear()
        self._refresh_case_folders(select_case_name=result["case_name"])
        self.status_label.setText(f"Created Smart Document Review folder:\n{result['case_folder']}")

    def _refresh_case_folders(self, select_case_name: str = "") -> None:
        current_name = select_case_name
        current_item = self.case_folder_list.currentItem()
        if not current_name and current_item:
            current_name = current_item.text()
        self.case_folder_list.blockSignals(True)
        self.case_folder_list.clear()
        for folder in list_smart_review_case_folders(self.project_root):
            item = QtWidgets.QListWidgetItem(folder["case_name"])
            item.setData(QtCore.Qt.UserRole, folder["case_folder"])
            self.case_folder_list.addItem(item)
            if current_name and folder["case_name"] == current_name:
                self.case_folder_list.setCurrentItem(item)
        self.case_folder_list.blockSignals(False)
        if self.case_folder_list.currentItem():
            self._load_selected_case_folder()

    def _load_selected_case_folder(self) -> None:
        case_folder = self._selected_case_folder_path()
        if not case_folder:
            return
        self.selected_case_folder = case_folder
        try:
            files = collect_review_documents_from_case_folder(case_folder, project_root=self.project_root)
        except Exception as exc:
            self._show_error("Load selected Smart Document Review folder", exc)
            return
        self.file_input.setPlainText("\n".join(str(path) for path in files))
        self.status_label.setText(
            f"Loaded {len(files)} supported source file(s) from selected folder only:\n{case_folder}"
        )

    def _open_selected_case_folder(self) -> None:
        case_folder = self._selected_case_folder_path()
        if not case_folder:
            self.status_label.setText("Select a Smart Document Review case folder first.")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(case_folder)))
        self.status_label.setText(f"Opened Smart Document Review folder:\n{case_folder}")

    def _selected_case_folder_path(self) -> Path | None:
        item = self.case_folder_list.currentItem()
        if not item:
            return None
        path = item.data(QtCore.Qt.UserRole)
        return Path(path) if path else None

    def _config_from_inputs(self) -> dict[str, str]:
        return {
            "state": self.state_input.text().strip(),
            "city": self.city_input.text().strip(),
            "county": self.county_input.text().strip(),
            "court_level": self.court_level_input.currentText().strip(),
            "court_name": self.court_name_input.text().strip(),
            "judge_name": self.judge_name_input.text().strip(),
            "attorney_or_requesting_party_name": self.requesting_party_input.text().strip(),
            "request_type": self.request_type_input.currentText().strip(),
            "filing_or_response_deadline": self.deadline_input.text().strip(),
            "procedural_posture": self.posture_input.toPlainText().strip(),
            "user_notes": self.notes_input.toPlainText().strip(),
        }

    def _export_existing_report(self, report_format: str) -> None:
        if not self.last_result:
            self.status_label.setText("Run a review before exporting.")
            return
        path = self.last_result.get("report_paths", {}).get(report_format)
        if not path:
            self.status_label.setText(f"{report_format.upper()} export is unavailable for this report.")
            return
        self.status_label.setText(f"{report_format.upper()} report already saved:\n{path}")

    def _export_generated_document(self, report_format: str) -> None:
        if not self.last_result:
            self.status_label.setText("Run a review before opening generated document exports.")
            return
        path = self.last_result.get("generated_document_paths", {}).get(report_format)
        if not path:
            self.status_label.setText(f"Generated {report_format.upper()} draft is unavailable for this review.")
            return
        generated = self.last_result.get("generated_document", {})
        self.status_label.setText(
            f"Generated draft {report_format.upper()} already saved:\n{path}\n"
            f"Certification status: {generated.get('certification_status', 'unknown')}."
        )

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self.export_json_button.setEnabled(enabled)
        self.export_markdown_button.setEnabled(enabled)
        self.export_pdf_button.setEnabled(enabled)
        self.generated_markdown_button.setEnabled(enabled)
        self.generated_pdf_button.setEnabled(enabled)

    def _show_error(self, action: str, exc: Exception) -> None:
        logger.exception("%s failed", action)
        message = f"{action} failed: {exc}"
        self.status_label.setText(message)
        self.output.setPlainText(message)

    def _use_vertical_scroll_only(self) -> None:
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.content_widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.layout.setSizeConstraint(QtWidgets.QLayout.SetDefaultConstraint)

    def _wrap_text_edit(self, text_edit: QtWidgets.QTextEdit) -> None:
        text_edit.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        text_edit.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        text_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
