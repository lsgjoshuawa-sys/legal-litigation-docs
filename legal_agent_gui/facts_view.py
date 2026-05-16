from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.intake import add_fact, delete_fact, list_facts, update_fact
from legal_agent.intake import list_evidence as _list_evidence
from .widgets import BaseView


class FactsView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Facts", "Capture facts and link them to evidence or relevance categories.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.fact_list = QtWidgets.QListWidget()
        self.fact_list.currentItemChanged.connect(self._load_fact)
        self.layout.addWidget(self.fact_list)
        self.date_input = QtWidgets.QLineEdit()
        self.fact_text_input = QtWidgets.QTextEdit()
        self.evidence_input = QtWidgets.QComboBox()
        self.relevance_input = QtWidgets.QLineEdit()
        self.save_button = QtWidgets.QPushButton("Save Fact")
        self.delete_button = QtWidgets.QPushButton("Delete Fact")
        self.save_button.clicked.connect(self._save_fact)
        self.delete_button.clicked.connect(self._delete_fact)
        form = QtWidgets.QFormLayout()
        form.addRow("Date:", self.date_input)
        form.addRow("Fact text:", self.fact_text_input)
        form.addRow("Linked evidence:", self.evidence_input)
        form.addRow("Relevance:", self.relevance_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.delete_button)
        self.current_fact_id: int | None = None

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _load_fact(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        fact = current.data(QtCore.Qt.UserRole)
        self.current_fact_id = fact["id"]
        self.date_input.setText(fact["date"] or "")
        self.fact_text_input.setPlainText(fact["fact_text"])
        self.relevance_input.setText(fact["relevance"])
        evidence_id = fact["source_evidence_id"]
        if evidence_id:
            self.evidence_input.setCurrentText(str(evidence_id))

    def _save_fact(self) -> None:
        if not self.case_id:
            return
        source_evidence_id = self.evidence_input.currentText().strip()
        source_id = int(source_evidence_id) if source_evidence_id.isdigit() else None
        if self.current_fact_id:
            update_fact(self.current_fact_id, self.date_input.text().strip(), self.fact_text_input.toPlainText().strip(), source_id, self.relevance_input.text().strip(), self.db_path)
        else:
            add_fact(self.case_id, self.fact_text_input.toPlainText().strip(), self.date_input.text().strip(), source_id, self.relevance_input.text().strip(), self.db_path)
        self._notify_case_data_changed(self.case_id)

    def _delete_fact(self) -> None:
        if self.current_fact_id:
            delete_fact(self.current_fact_id, self.db_path)
            self.current_fact_id = None
            self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        selected_id = self.current_fact_id
        self.fact_list.clear()
        self.evidence_input.clear()
        if not self.case_id:
            return
        for evidence in _list_evidence(self.case_id, self.db_path):
            self.evidence_input.addItem(str(evidence["id"]))
        for fact in list_facts(self.case_id, self.db_path):
            item = QtWidgets.QListWidgetItem(f"{fact['date']}: {fact['fact_text'][:60]}")
            item.setData(QtCore.Qt.UserRole, fact)
            self.fact_list.addItem(item)
            if selected_id and fact["id"] == selected_id:
                self.fact_list.setCurrentItem(item)

    def select_record(self, record_id: int) -> bool:
        for index in range(self.fact_list.count()):
            item = self.fact_list.item(index)
            fact = item.data(QtCore.Qt.UserRole)
            if fact and fact["id"] == record_id:
                self.fact_list.setCurrentItem(item)
                self._load_fact(item)
                return True
        return False
