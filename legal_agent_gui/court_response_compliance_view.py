from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6 import QtWidgets

from legal_agent.court_response_compliance import (
    COURT_LEVEL_CHOICES,
    DISCLAIMER,
    FEATURE_NAME,
    REQUEST_TYPE_CHOICES,
    report_to_markdown,
    run_court_response_compliance_review,
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

        self.file_input = QtWidgets.QTextEdit()
        self.file_input.setPlaceholderText("/path/to/response-document.pdf")
        self.file_input.setMaximumHeight(90)
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self._browse_document)
        file_row = QtWidgets.QHBoxLayout()
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
        self.notes_input = QtWidgets.QTextEdit()
        self.notes_input.setPlaceholderText("User notes, court request context, filing instructions, or known concerns")

        form = QtWidgets.QFormLayout()
        form.addRow("Document to review:", file_row)
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

        self.review_button = QtWidgets.QPushButton("Run Court Response Compliance Review")
        self.export_json_button = QtWidgets.QPushButton("Export JSON")
        self.export_markdown_button = QtWidgets.QPushButton("Export Markdown")
        self.export_pdf_button = QtWidgets.QPushButton("Export PDF")
        self.generated_markdown_button = QtWidgets.QPushButton("Generated Draft Markdown")
        self.generated_pdf_button = QtWidgets.QPushButton("Generated Draft PDF")
        self.review_button.clicked.connect(self._run_review)
        self.export_json_button.clicked.connect(lambda: self._export_existing_report("json"))
        self.export_markdown_button.clicked.connect(lambda: self._export_existing_report("markdown"))
        self.export_pdf_button.clicked.connect(lambda: self._export_existing_report("pdf"))
        self.generated_markdown_button.clicked.connect(lambda: self._export_generated_document("markdown"))
        self.generated_pdf_button.clicked.connect(lambda: self._export_generated_document("pdf"))

        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.review_button)
        button_row.addWidget(self.export_json_button)
        button_row.addWidget(self.export_markdown_button)
        button_row.addWidget(self.export_pdf_button)
        button_row.addWidget(self.generated_markdown_button)
        button_row.addWidget(self.generated_pdf_button)
        button_row.addStretch(1)
        self.layout.addLayout(button_row)

        self.status_label = QtWidgets.QLabel(DISCLAIMER)
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)

        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(360)
        self.layout.addWidget(self.output)
        self._set_export_buttons_enabled(False)

    def refresh(self) -> None:
        self._set_export_buttons_enabled(bool(self.last_result))

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
                self.status_label.setText("Document(s) selected. Complete jurisdiction fields to run the review.")
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
            "Review complete. Standalone report saved separately from case records. "
            f"Strict gate accepted={gate.get('accepted', False)}. "
            f"JSON: {paths.get('json', 'unavailable')} "
            f"Generated draft: {generated_paths.get('markdown', 'unavailable')}"
        )
        self._set_export_buttons_enabled(True)

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
        self.status_label.setText(f"{report_format.upper()} report already saved: {path}")

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
            f"Generated draft {report_format.upper()} already saved: {path}. "
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
