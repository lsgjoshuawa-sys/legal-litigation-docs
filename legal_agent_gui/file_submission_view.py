from __future__ import annotations

from pathlib import Path

from PySide6 import QtWidgets

from legal_agent.logger import get_logger
from legal_agent.file_submission import (
    HANDLER_CHOICES,
    HANDLER_EVIDENCE,
    data_extraction_recommendation,
    infer_document_topic,
    is_data_extraction_compatible,
    read_file_preview,
    submit_file_to_handler,
)
from .widgets import BaseView


logger = get_logger("legal_agent.gui.file_submission")


class FileSubmissionView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(
            "File Submission",
            "Add a file to the active case and route it to the best topic handler.",
        )
        self.db_path = db_path
        self.case_id: int | None = None
        self.last_handler: str | None = None

        self.file_input = QtWidgets.QLineEdit()
        self.file_input.setPlaceholderText("/path/to/document.pdf")
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self._browse_file)

        file_row = QtWidgets.QHBoxLayout()
        file_row.addWidget(self.file_input, 1)
        file_row.addWidget(self.browse_button)

        self.title_input = QtWidgets.QLineEdit()
        self.title_input.setPlaceholderText("Short title for the submitted file")
        self.notes_input = QtWidgets.QTextEdit()
        self.notes_input.setPlaceholderText("Optional notes, source context, deadline clues, or routing instructions.")

        self.detected_label = QtWidgets.QLabel("Detected topic: Not analyzed")
        self.route_input = QtWidgets.QComboBox()
        self.route_input.addItems(HANDLER_CHOICES)
        self.route_input.setCurrentText(HANDLER_EVIDENCE)
        self.extract_data_input = QtWidgets.QCheckBox("Extract case details from compatible text file")
        self.extract_data_input.setChecked(False)
        self.extract_data_input.setEnabled(False)
        self.compatibility_label = QtWidgets.QLabel(
            "Data extraction works with TXT, Markdown, CSV, JSON, XML, HTML, HTM, and RTF."
        )
        self.compatibility_label.setWordWrap(True)

        self.preview_input = QtWidgets.QTextEdit()
        self.preview_input.setPlaceholderText("Text preview appears here for readable text files.")

        self.analyze_button = QtWidgets.QPushButton("Analyze File")
        self.submit_button = QtWidgets.QPushButton("Submit to Handler")
        self.open_handler_button = QtWidgets.QPushButton("Open Routed Handler")
        self.open_handler_button.setToolTip(
            "Open the selected route. After submitting, the saved record will be selected when possible."
        )
        self.analyze_button.clicked.connect(self._analyze_file)
        self.submit_button.clicked.connect(self._submit_file)
        self.open_handler_button.clicked.connect(self._open_current_handler)

        form = QtWidgets.QFormLayout()
        form.addRow("File:", file_row)
        form.addRow("Title:", self.title_input)
        form.addRow("Submission notes:", self.notes_input)
        form.addRow("Detected topic:", self.detected_label)
        form.addRow("Route to:", self.route_input)
        form.addRow("Data extraction:", self.extract_data_input)
        form.addRow("Compatible types:", self.compatibility_label)
        form.addRow("Preview:", self.preview_input)
        self.layout.addLayout(form)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.analyze_button)
        button_row.addWidget(self.submit_button)
        button_row.addWidget(self.open_handler_button)
        button_row.addStretch(1)
        self.layout.addLayout(button_row)

        self.message_label = QtWidgets.QLabel("")
        self.message_label.setWordWrap(True)
        self.layout.addWidget(self.message_label)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _browse_file(self) -> None:
        try:
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Select file to submit",
                str(Path.home()),
                "All files (*.*)",
            )
            if not file_path:
                return
            self.file_input.setText(file_path)
            if not self.title_input.text().strip():
                self.title_input.setText(Path(file_path).stem)
            self._analyze_file()
        except Exception as exc:
            self._show_action_error("Browse file", exc)

    def _analyze_file(self) -> None:
        try:
            self._analyze_file_impl()
        except Exception as exc:
            self._show_action_error("Analyze file", exc)

    def _analyze_file_impl(self) -> None:
        path = Path(self.file_input.text().strip()).expanduser()
        if not path.exists() or not path.is_file():
            self._set_message("Choose an existing file first.", is_error=True)
            self.detected_label.setText("Detected topic: Not analyzed")
            return

        preview = read_file_preview(path)
        self.preview_input.setPlainText(preview)
        compatible = is_data_extraction_compatible(path)
        self.extract_data_input.setEnabled(compatible)
        self.extract_data_input.setChecked(compatible)
        self.compatibility_label.setText(data_extraction_recommendation(path))
        suggestion = infer_document_topic(path, preview)
        self.route_input.setCurrentText(suggestion.handler)
        reason_text = "; ".join(suggestion.reasons)
        self.detected_label.setText(
            f"{suggestion.handler} ({suggestion.confidence} confidence) - {reason_text}"
        )
        self._set_message("File analyzed. Review the route before submitting.")

    def _submit_file(self) -> None:
        try:
            self._submit_file_impl()
        except Exception as exc:
            self._show_action_error("Submit file", exc)

    def _submit_file_impl(self) -> None:
        if not self.case_id:
            self._set_message("Select an active case before submitting a file.", is_error=True)
            return
        path = Path(self.file_input.text().strip()).expanduser()
        if not path.exists() or not path.is_file():
            self._set_message("Choose an existing file before submitting.", is_error=True)
            return

        preview = self.preview_input.toPlainText().strip()
        if not preview:
            preview = read_file_preview(path)
        extract_data = self.extract_data_input.isChecked() and is_data_extraction_compatible(path)
        result = submit_file_to_handler(
            case_id=self.case_id,
            file_path=path,
            handler=self.route_input.currentText(),
            title=self.title_input.text().strip(),
            notes=self.notes_input.toPlainText().strip(),
            preview_text=preview,
            extract_data=extract_data,
            db_path=self.db_path,
        )
        self.last_handler = result.handler
        self._set_message(result.message)
        self._notify_case_data_changed(self.case_id)
        self._open_routed_handler(result.record_id)

    def _open_current_handler(self) -> None:
        try:
            self._open_routed_handler()
        except Exception as exc:
            self._show_action_error("Open routed handler", exc)

    def _open_routed_handler(self, record_id: int | None = None) -> None:
        handler = self.last_handler if record_id is not None else self.route_input.currentText()
        if not handler:
            return
        window = self.window()
        sidebar = getattr(window, "sidebar", None)
        views = getattr(window, "views", {})
        if sidebar is None or handler not in views:
            self._set_message(f"Route '{handler}' is not available in this window.", is_error=True)
            return
        row = list(views).index(handler)
        sidebar.setCurrentRow(row)
        routed_view = views[handler]
        if record_id is not None and hasattr(routed_view, "select_record"):
            routed_view.select_record(record_id)
        if record_id is None:
            self._set_message(f"Opened {handler}.")

    def refresh(self) -> None:
        if self.case_id:
            self.submit_button.setEnabled(True)
            self.submit_button.setToolTip("")
        else:
            self.submit_button.setEnabled(False)
            self.submit_button.setToolTip("Select an active case before submitting files.")
            self._set_message("Select an active case before submitting files.", is_error=True)

    def _set_message(self, text: str, is_error: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setStyleSheet("color: #b00020;" if is_error else "")
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(text)

    def _show_action_error(self, action: str, exc: Exception) -> None:
        logger.exception("%s failed in File Submission view", action)
        self._set_message(f"{action} failed: {exc}", is_error=True)
