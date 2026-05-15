from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.drafting import generate_outline
from .widgets import BaseView


class FilingChecklistView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Filing Readiness Checklist", "Review the filing readiness outline and verify required checklist items.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(320)
        self.refresh_button = QtWidgets.QPushButton("Refresh Filing Checklist")
        self.refresh_button.clicked.connect(self.refresh)
        self.layout.addWidget(self.output)
        self.layout.addWidget(self.refresh_button)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def refresh(self) -> None:
        self.output.clear()
        if not self.case_id:
            self.output.setPlainText("Select a case first.")
            return
        outline = generate_outline(self.case_id, "filing checklist", self.db_path)
        if not outline.get("outline"):
            self.output.setPlainText("No filing checklist available.")
            return
        lines = ["Filing checklist outline:", *[f"- {section}" for section in outline["outline"]]]
        self.output.setPlainText("\n".join(lines))
