from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.intake import add_party, delete_party, list_parties, update_party
from .widgets import BaseView


class PartiesView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Parties", "Manage plaintiffs, defendants, and other parties involved in the case.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.party_list = QtWidgets.QListWidget()
        self.party_list.currentItemChanged.connect(self._load_party)
        self.layout.addWidget(self.party_list)
        self.name_input = QtWidgets.QLineEdit()
        self.role_input = QtWidgets.QLineEdit()
        self.type_input = QtWidgets.QLineEdit()
        self.notes_input = QtWidgets.QTextEdit()
        self.save_button = QtWidgets.QPushButton("Save Party")
        self.delete_button = QtWidgets.QPushButton("Delete Party")
        self.save_button.clicked.connect(self._save_party)
        self.delete_button.clicked.connect(self._delete_party)
        form = QtWidgets.QFormLayout()
        form.addRow("Name:", self.name_input)
        form.addRow("Role:", self.role_input)
        form.addRow("Type:", self.type_input)
        form.addRow("Notes:", self.notes_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.delete_button)
        self.current_party_id: int | None = None

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _load_party(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        party = current.data(QtCore.Qt.UserRole)
        self.current_party_id = party.id
        self.name_input.setText(party.name)
        self.role_input.setText(party.role)
        self.type_input.setText(party.type)
        self.notes_input.setPlainText(party.notes)

    def _save_party(self) -> None:
        if not self.case_id:
            return
        name = self.name_input.text().strip()
        if self.current_party_id:
            update_party(self.current_party_id, name, self.role_input.text().strip(), self.type_input.text().strip(), self.notes_input.toPlainText().strip(), self.db_path)
        else:
            add_party(self.case_id, name, self.role_input.text().strip(), self.type_input.text().strip(), self.notes_input.toPlainText().strip(), self.db_path)
        self._notify_case_data_changed(self.case_id)

    def _delete_party(self) -> None:
        if self.current_party_id:
            delete_party(self.current_party_id, self.db_path)
            self.current_party_id = None
            self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        self.party_list.clear()
        if not self.case_id:
            return
        for party in list_parties(self.case_id, self.db_path):
            item = QtWidgets.QListWidgetItem(f"{party.name} ({party.role})")
            item.setData(QtCore.Qt.UserRole, party)
            self.party_list.addItem(item)
