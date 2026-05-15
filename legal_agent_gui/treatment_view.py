from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.treatment import get_treatment_status, set_treatment_status
from .widgets import BaseView


class TreatmentView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Citation Treatment Checker", "Track treatment status of legal authorities and warn on unknown treatment.")
        self.db_path = db_path
        self.authority_id_input = QtWidgets.QLineEdit()
        self.status_input = QtWidgets.QComboBox()
        self.status_input.addItems(["unknown", "controlling", "persuasive", "distinguished", "criticized", "overruled", "partially overruled", "superseded", "vacated"])
        self.notes_input = QtWidgets.QTextEdit()
        self.save_button = QtWidgets.QPushButton("Set Treatment Status")
        self.save_button.clicked.connect(self._save_status)
        self.status_label = QtWidgets.QLabel("")
        form = QtWidgets.QFormLayout()
        form.addRow("Authority ID:", self.authority_id_input)
        form.addRow("Treatment status:", self.status_input)
        form.addRow("Notes:", self.notes_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.status_label)

    def _save_status(self) -> None:
        authority_id = self.authority_id_input.text().strip()
        if not authority_id.isdigit():
            self.status_label.setText("Enter a numeric authority ID.")
            return
        ok = set_treatment_status(int(authority_id), self.status_input.currentText(), self.notes_input.toPlainText().strip(), self.db_path)
        self.status_label.setText("Treatment updated." if ok else "Authority not found.")
        if ok:
            self._notify_case_data_changed()

    def refresh(self) -> None:
        self.status_label.setText("Enter an authority ID and treatment status to update.")
