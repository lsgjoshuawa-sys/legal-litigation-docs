from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.intake import add_evidence, delete_evidence, list_evidence, update_evidence
from .plain_text_lists import json_list_from_plain_text, plain_text_from_list_storage
from .widgets import BaseView


class EvidenceView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Evidence", "Manage evidence items and their links to claims and admissibility notes.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.evidence_list = QtWidgets.QListWidget()
        self.evidence_list.currentItemChanged.connect(self._load_evidence)
        self.layout.addWidget(self.evidence_list)
        self.title_input = QtWidgets.QLineEdit()
        self.type_input = QtWidgets.QLineEdit()
        self.description_input = QtWidgets.QTextEdit()
        self.file_input = QtWidgets.QLineEdit()
        self.date_input = QtWidgets.QLineEdit()
        self.supports_input = QtWidgets.QTextEdit()
        self.supports_input.setPlaceholderText("One supported claim or defense per line, e.g.\nBreach of Contract\nNegligence")
        self.admissibility_input = QtWidgets.QTextEdit()
        self.weakness_input = QtWidgets.QTextEdit()
        self.save_button = QtWidgets.QPushButton("Save Evidence")
        self.delete_button = QtWidgets.QPushButton("Delete Evidence")
        self.save_button.clicked.connect(self._save_evidence)
        self.delete_button.clicked.connect(self._delete_evidence)
        form = QtWidgets.QFormLayout()
        form.addRow("Title:", self.title_input)
        form.addRow("Evidence type:", self.type_input)
        form.addRow("Description:", self.description_input)
        form.addRow("File path:", self.file_input)
        form.addRow("Date obtained:", self.date_input)
        form.addRow("Supported claims:", self.supports_input)
        form.addRow("Admissibility notes:", self.admissibility_input)
        form.addRow("Weakness notes:", self.weakness_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.delete_button)
        self.current_evidence_id: int | None = None

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _load_evidence(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        evidence = current.data(QtCore.Qt.UserRole)
        self.current_evidence_id = evidence["id"]
        self.title_input.setText(evidence["title"])
        self.type_input.setText(evidence["evidence_type"])
        self.description_input.setPlainText(evidence["description"])
        self.file_input.setText(evidence["file_path"])
        self.date_input.setText(evidence["date_obtained"])
        self.supports_input.setPlainText(plain_text_from_list_storage(evidence["supports_claims_json"]))
        self.admissibility_input.setPlainText(evidence["admissibility_notes"])
        self.weakness_input.setPlainText(evidence["weakness_notes"])

    def _save_evidence(self) -> None:
        if not self.case_id:
            return
        payload = {
            "title": self.title_input.text().strip(),
            "evidence_type": self.type_input.text().strip(),
            "description": self.description_input.toPlainText().strip(),
            "file_path": self.file_input.text().strip(),
            "date_obtained": self.date_input.text().strip(),
            "supports_claims_json": json_list_from_plain_text(self.supports_input.toPlainText()),
            "admissibility_notes": self.admissibility_input.toPlainText().strip(),
            "weakness_notes": self.weakness_input.toPlainText().strip(),
        }
        if self.current_evidence_id:
            update_evidence(self.current_evidence_id, **payload, db_path=self.db_path)
        else:
            add_evidence(self.case_id, **payload, db_path=self.db_path)
        self._notify_case_data_changed(self.case_id)

    def _delete_evidence(self) -> None:
        if self.current_evidence_id:
            delete_evidence(self.current_evidence_id, self.db_path)
            self.current_evidence_id = None
            self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        selected_id = self.current_evidence_id
        self.evidence_list.clear()
        if not self.case_id:
            return
        for evidence in list_evidence(self.case_id, self.db_path):
            item = QtWidgets.QListWidgetItem(f"{evidence['title']} ({evidence['evidence_type']})")
            item.setData(QtCore.Qt.UserRole, evidence)
            self.evidence_list.addItem(item)
            if selected_id and evidence["id"] == selected_id:
                self.evidence_list.setCurrentItem(item)

    def select_record(self, record_id: int) -> bool:
        for index in range(self.evidence_list.count()):
            item = self.evidence_list.item(index)
            evidence = item.data(QtCore.Qt.UserRole)
            if evidence and evidence["id"] == record_id:
                self.evidence_list.setCurrentItem(item)
                self._load_evidence(item)
                return True
        return False
