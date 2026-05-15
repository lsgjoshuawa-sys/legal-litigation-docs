from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.export import export_case
from .widgets import BaseView


class ExportView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Export Center", "Export case work product to Markdown or JSON for review and filing preparation.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.format_input = QtWidgets.QComboBox()
        self.format_input.addItems(["markdown", "json"])
        self.output_path_input = QtWidgets.QLineEdit()
        self.output_path_input.setPlaceholderText("export.md")
        self.export_button = QtWidgets.QPushButton("Export Case")
        self.export_button.clicked.connect(self._export_case)
        self.message_label = QtWidgets.QLabel("")
        self.output_display = QtWidgets.QTextEdit(readOnly=True)
        self.output_display.setMinimumHeight(240)
        form = QtWidgets.QFormLayout()
        form.addRow("Export format:", self.format_input)
        form.addRow("Output path:", self.output_path_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.export_button)
        self.layout.addWidget(self.message_label)
        self.layout.addWidget(self.output_display)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _export_case(self) -> None:
        self.message_label.clear()
        self.output_display.clear()
        if not self.case_id:
            self.message_label.setText("Select a case first.")
            return
        export_format = self.format_input.currentText()
        path = self.output_path_input.text().strip() or None
        try:
            result = export_case(self.case_id, export_format, path, self.db_path)
            if path:
                self.message_label.setText(f"Export saved to {path}")
            else:
                self.message_label.setText("Export completed.")
                self.output_display.setPlainText(result)
        except Exception as exc:
            self.message_label.setText(f"Export failed: {exc}")

    def refresh(self) -> None:
        self.output_display.clear()
        self.message_label.clear()
