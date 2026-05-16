from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.intake import add_claim, delete_claim, list_claims, update_claim
from .plain_text_lists import json_list_from_plain_text, plain_text_from_list_storage
from .widgets import BaseView


class ClaimsView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Claims / Defenses", "Define claims, defenses, and required elements with supporting connections.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.claim_list = QtWidgets.QListWidget()
        self.claim_list.currentItemChanged.connect(self._load_claim)
        self.layout.addWidget(self.claim_list)
        self.name_input = QtWidgets.QLineEdit()
        self.type_input = QtWidgets.QLineEdit()
        self.basis_input = QtWidgets.QLineEdit()
        self.required_input = QtWidgets.QTextEdit()
        self.required_input.setPlaceholderText("One required element per line, e.g.\nDuty\nBreach\nCausation\nDamages")
        self.status_input = QtWidgets.QLineEdit()
        self.notes_input = QtWidgets.QTextEdit()
        self.save_button = QtWidgets.QPushButton("Save Claim")
        self.delete_button = QtWidgets.QPushButton("Delete Claim")
        self.save_button.clicked.connect(self._save_claim)
        self.delete_button.clicked.connect(self._delete_claim)
        form = QtWidgets.QFormLayout()
        form.addRow("Claim name:", self.name_input)
        form.addRow("Claim type:", self.type_input)
        form.addRow("Jurisdiction basis:", self.basis_input)
        form.addRow("Required elements:", self.required_input)
        form.addRow("Status:", self.status_input)
        form.addRow("Notes:", self.notes_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.delete_button)
        self.current_claim_id: int | None = None

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _load_claim(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        claim = current.data(QtCore.Qt.UserRole)
        self.current_claim_id = claim["id"]
        self.name_input.setText(claim["claim_name"])
        self.type_input.setText(claim["claim_type"])
        self.basis_input.setText(claim["jurisdiction_basis"])
        self.required_input.setPlainText(plain_text_from_list_storage(claim["required_elements_json"]))
        self.status_input.setText(claim["status"])
        self.notes_input.setPlainText(claim["notes"])

    def _save_claim(self) -> None:
        if not self.case_id:
            return
        required_elements = json_list_from_plain_text(self.required_input.toPlainText())
        if self.current_claim_id:
            update_claim(self.current_claim_id, self.name_input.text().strip(), self.type_input.text().strip(), self.basis_input.text().strip(), required_elements, self.status_input.text().strip(), self.notes_input.toPlainText().strip(), self.db_path)
        else:
            add_claim(self.case_id, self.name_input.text().strip(), self.type_input.text().strip(), self.basis_input.text().strip(), required_elements, self.status_input.text().strip(), self.notes_input.toPlainText().strip(), self.db_path)
        self._notify_case_data_changed(self.case_id)

    def _delete_claim(self) -> None:
        if self.current_claim_id:
            delete_claim(self.current_claim_id, self.db_path)
            self.current_claim_id = None
            self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        self.claim_list.clear()
        if not self.case_id:
            return
        for claim in list_claims(self.case_id, self.db_path):
            item = QtWidgets.QListWidgetItem(f"{claim['claim_name']} ({claim['status']})")
            item.setData(QtCore.Qt.UserRole, claim)
            self.claim_list.addItem(item)
