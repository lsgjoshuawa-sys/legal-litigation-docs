from __future__ import annotations

import json
from typing import Any

from PySide6 import QtCore, QtWidgets

from legal_agent.case_folders import (
    SECTION_LABELS,
    case_folder_status,
    list_case_extractions,
    scan_all_case_folders,
    scan_case_folder,
)
from legal_agent.intake import list_action_items, list_claims, list_evidence, list_facts, list_parties
from legal_agent.logger import get_logger
from .widgets import BaseView

logger = get_logger(__name__)


class CaseFolderIntakeView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(
            "Case Folder Intake",
            "Review case-folder file intake, AI extraction status, and source-linked section records.",
        )
        self.db_path = db_path
        self.case_id: int | None = None

        self.path_label = QtWidgets.QLabel("No active case selected.")
        self.path_label.setWordWrap(True)
        self.layout.addWidget(self.path_label)

        button_row = QtWidgets.QHBoxLayout()
        self.scan_case_button = QtWidgets.QPushButton("Scan Active Case Folder")
        self.scan_all_button = QtWidgets.QPushButton("Scan All Case Folders")
        self.scan_case_button.clicked.connect(self._scan_case)
        self.scan_all_button.clicked.connect(self._scan_all)
        button_row.addWidget(self.scan_case_button)
        button_row.addWidget(self.scan_all_button)
        button_row.addStretch(1)
        self.layout.addLayout(button_row)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.manual_summary = QtWidgets.QTextEdit(readOnly=True)
        self.manual_summary.setPlaceholderText("Manual case data appears here.")
        self.extraction_list = QtWidgets.QListWidget()
        self.extraction_list.currentItemChanged.connect(self._load_extraction)
        self.extraction_detail = QtWidgets.QTextEdit(readOnly=True)
        self.extraction_detail.setPlaceholderText("Select an AI extraction record to inspect details.")
        splitter.addWidget(self.manual_summary)
        splitter.addWidget(self.extraction_list)
        splitter.addWidget(self.extraction_detail)
        splitter.setSizes([320, 360, 520])
        self.layout.addWidget(splitter)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _scan_case(self) -> None:
        if not self.case_id:
            self._set_message("Select an active case before scanning.", is_error=True)
            return
        try:
            result = scan_case_folder(self.case_id, db_path=self.db_path)
            warning = f" Warning: {'; '.join(result.warnings)}" if result.warnings else ""
            self._set_message(f"Active case scan complete: {result.summary()}.{warning}")
            self.refresh()
        except Exception as exc:
            logger.exception("Active case folder scan failed")
            self._set_message(f"Case folder scan failed: {exc}", is_error=True)

    def _scan_all(self) -> None:
        try:
            result = scan_all_case_folders(db_path=self.db_path)
            warning = f" Warning: {'; '.join(result.warnings)}" if result.warnings else ""
            self._set_message(f"All case folders scanned: {result.summary()}.{warning}")
            self.refresh()
        except Exception as exc:
            logger.exception("All case folder scan failed")
            self._set_message(f"All-folder scan failed: {exc}", is_error=True)

    def refresh(self) -> None:
        self.extraction_list.clear()
        self.extraction_detail.clear()
        if not self.case_id:
            self.path_label.setText("No active case selected.")
            self.manual_summary.clear()
            self.scan_case_button.setEnabled(False)
            return

        self.scan_case_button.setEnabled(True)
        try:
            status = case_folder_status(self.case_id, self.db_path)
            self.path_label.setText(f"Case folder: {status['case_directory']}")
            self.manual_summary.setPlainText(self._manual_case_text())
            records = sorted(
                list_case_extractions(self.case_id, self.db_path),
                key=lambda record: str(record.get("extracted_at") or ""),
                reverse=True,
            )
            for record in records:
                confidence = record.get("confidence_score", 0.0)
                try:
                    confidence_text = f"{float(confidence):.2f}"
                except (TypeError, ValueError):
                    confidence_text = "0.00"
                review = "review" if record.get("review_needed") else "ok"
                text = (
                    f"{record.get('source_file_name', 'unknown')} | "
                    f"{record.get('source_section_label', record.get('source_section_folder', ''))} | "
                    f"{record.get('status', 'unknown')} | confidence {confidence_text} | {review}"
                )
                item = QtWidgets.QListWidgetItem(text)
                item.setData(QtCore.Qt.UserRole, record)
                self.extraction_list.addItem(item)

            self._set_message(
                "Manifest: "
                f"{status['files']} files, {status['extractions']} extraction records, "
                f"{status['pending_extractions']} pending, {status['duplicate_files']} duplicates, "
                f"{status['quarantined_files']} quarantined, {status['failed_files']} failed."
            )
        except Exception as exc:
            logger.exception("Case folder intake refresh failed")
            self._set_message(f"Unable to load case folder intake status: {exc}", is_error=True)

    def _manual_case_text(self) -> str:
        if not self.case_id:
            return ""
        sections: list[str] = ["Manual Case Data", ""]
        sections.extend(self._records_block("Parties", [f"{party['name']} ({party['role'] or 'role unknown'})" for party in list_parties(self.case_id, self.db_path)]))
        sections.extend(self._records_block("Facts", [f"{fact['date'] or 'undated'}: {fact['fact_text']}" for fact in list_facts(self.case_id, self.db_path)]))
        sections.extend(self._records_block("Claims / Defenses", [f"{claim['claim_name']} ({claim['claim_type'] or 'type unknown'})" for claim in list_claims(self.case_id, self.db_path)]))
        sections.extend(self._records_block("Evidence", [f"{evidence['title']} ({evidence['evidence_type'] or 'type unknown'})" for evidence in list_evidence(self.case_id, self.db_path)]))
        sections.extend(self._records_block("Action Items & Due Dates", [f"{item['due_date'] or 'no date'}: {item['action_text']}" for item in list_action_items(self.case_id, self.db_path)]))
        sections.append("")
        sections.append("AI-extracted data is stored separately in the case folder manifest and does not overwrite these manual records.")
        return "\n".join(sections)

    def _records_block(self, title: str, records: list[str]) -> list[str]:
        lines = [title + ":"]
        if not records:
            lines.append("- none")
        else:
            for value in records[:12]:
                compact = value.replace("\n", " ").strip()
                lines.append(f"- {compact[:220]}")
            if len(records) > 12:
                lines.append(f"- ... {len(records) - 12} more")
        lines.append("")
        return lines

    def _load_extraction(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        record = current.data(QtCore.Qt.UserRole)
        self.extraction_detail.setPlainText(self._format_extraction(record))

    def _format_extraction(self, record: dict[str, Any]) -> str:
        extraction = record.get("extraction") if isinstance(record.get("extraction"), dict) else {}
        lines = [
            "AI Extraction",
            "",
            f"Source file: {record.get('source_file_name', '')}",
            f"Source path: {record.get('source_original_path', '')}",
            f"Source section: {record.get('source_section_folder', '')} ({record.get('source_section_label', '')})",
            f"Primary target section: {record.get('target_section_folder', '')} ({record.get('target_section_label', '')})",
            f"Recommended destination: {record.get('recommended_destination_section', '')} ({record.get('recommended_destination_label', '')})",
            f"Status: {record.get('status', '')}",
            f"Confidence score: {record.get('confidence_score', 0.0)}",
            f"Review needed: {'yes' if record.get('review_needed') else 'no'}",
            f"Provider: {record.get('ai_provider', '')}",
            f"Extracted at: {record.get('extracted_at', '')}",
            "",
            "Summary:",
            str(extraction.get("summary") or ""),
            "",
        ]
        for key, label in [
            ("key_facts", "Key Facts"),
            ("parties_mentioned", "Parties Mentioned"),
            ("dates_and_deadlines", "Dates and Deadlines"),
            ("evidence_references", "Evidence References"),
            ("claims_or_defenses_mentioned", "Claims or Defenses Mentioned"),
            ("jurisdiction_clues", "Jurisdiction Clues"),
            ("procedural_issues", "Procedural Issues"),
            ("legal_authorities_cited", "Legal Authorities Cited"),
            ("action_items", "Action Items"),
            ("extraction_warnings", "Extraction Warnings"),
        ]:
            lines.append(label + ":")
            values = extraction.get(key) or record.get(key) or []
            if not isinstance(values, list):
                values = [values]
            if values:
                lines.extend(f"- {str(value)}" for value in values)
            else:
                lines.append("- none")
            lines.append("")
        lines.append("Raw extraction JSON:")
        lines.append(json.dumps(extraction, indent=2, sort_keys=True))
        return "\n".join(lines)

    def _set_message(self, text: str, is_error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #b00020;" if is_error else "")
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(text)
