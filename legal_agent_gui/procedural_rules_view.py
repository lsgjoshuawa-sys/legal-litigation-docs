from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.jurisdiction import get_procedural_rules
from .widgets import BaseView


class ProceduralRulesView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Procedural Rules", "Review rules that apply based on the current jurisdiction classification.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.rules_output = QtWidgets.QTextEdit(readOnly=True)
        self.rules_output.setMinimumHeight(240)
        self.refresh_button = QtWidgets.QPushButton("Refresh Procedural Rules")
        self.refresh_button.clicked.connect(self.refresh)
        self.layout.addWidget(self.rules_output)
        self.layout.addWidget(self.refresh_button)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def refresh(self) -> None:
        self.rules_output.clear()
        if not self.case_id:
            self.rules_output.setPlainText("Select a case first.")
            return
        result = get_procedural_rules(self.case_id, self.db_path)
        if not result.get("rules"):
            self.rules_output.setPlainText(result.get("note", "No procedural rules found."))
            return
        lines = ["Applicable procedural rules:", *[f"- {rule}" for rule in result["rules"]]]
        self.rules_output.setPlainText("\n".join(lines))
