from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.authority_validation import add_authority, get_authority, list_authorities, verify_authority
from legal_agent.jurisdiction import classify_case
from .widgets import BaseView


class AuthorityValidationView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Authority Validation", "Enter and verify authorities. Only verified authorities may be used in final drafts.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.layout.addWidget(QtWidgets.QLabel("Selected case must be chosen from the top selector before using this page."))
        self.list_widget = QtWidgets.QListWidget()
        self.layout.addWidget(self.list_widget)
        self.add_button = QtWidgets.QPushButton("Add Authority")
        self.verify_button = QtWidgets.QPushButton("Mark Verified")
        self.add_button.clicked.connect(self._add_authority)
        self.verify_button.clicked.connect(self._verify_selected)
        self.button_bar = QtWidgets.QHBoxLayout()
        self.button_bar.addWidget(self.add_button)
        self.button_bar.addWidget(self.verify_button)
        self.layout.addLayout(self.button_bar)
        self.warning_label = QtWidgets.QLabel("")
        self.layout.addWidget(self.warning_label)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _add_authority(self) -> None:
        if not self.case_id:
            return
        dialog = AuthorityDialog(self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            data = dialog.data
            add_authority(self.case_id, **data, db_path=self.db_path)
            self._notify_case_data_changed(self.case_id)

    def _verify_selected(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            self.warning_label.setText("Select an authority to verify.")
            return
        authority_id = item.data(QtCore.Qt.UserRole)
        if verify_authority(authority_id, True, self.db_path):
            self.warning_label.setText("Authority verified.")
        else:
            self.warning_label.setText("Unable to verify authority. Ensure required fields are complete.")
        self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        selected_id = self.list_widget.currentItem().data(QtCore.Qt.UserRole) if self.list_widget.currentItem() else None
        self.list_widget.clear()
        if not self.case_id:
            return
        authorities = list_authorities(self.case_id, self.db_path)
        for auth in authorities:
            status = "Verified" if auth["verified"] else "Unverified"
            item = QtWidgets.QListWidgetItem(f"[{status}] {auth['title']} ({auth['citation']})")
            item.setData(QtCore.Qt.UserRole, auth["id"])
            self.list_widget.addItem(item)
            if selected_id and auth["id"] == selected_id:
                self.list_widget.setCurrentItem(item)

    def select_record(self, record_id: int) -> bool:
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.data(QtCore.Qt.UserRole) == record_id:
                self.list_widget.setCurrentItem(item)
                return True
        return False


class AuthorityDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Authority")
        self.data: dict[str, str] = {}
        layout = QtWidgets.QFormLayout(self)
        self.type_input = QtWidgets.QLineEdit()
        self.title_input = QtWidgets.QLineEdit()
        self.citation_input = QtWidgets.QLineEdit()
        self.jurisdiction_input = QtWidgets.QLineEdit()
        self.court_input = QtWidgets.QLineEdit()
        self.year_input = QtWidgets.QLineEdit()
        self.source_input = QtWidgets.QLineEdit()
        self.excerpt_input = QtWidgets.QTextEdit()
        self.treatment_input = QtWidgets.QComboBox()
        self.treatment_input.addItems(["unknown", "controlling", "persuasive", "distinguished", "criticized", "overruled", "partially overruled", "superseded", "vacated"])
        self.notes_input = QtWidgets.QTextEdit()
        layout.addRow("Authority type:", self.type_input)
        layout.addRow("Title:", self.title_input)
        layout.addRow("Citation:", self.citation_input)
        layout.addRow("Jurisdiction:", self.jurisdiction_input)
        layout.addRow("Court:", self.court_input)
        layout.addRow("Year:", self.year_input)
        layout.addRow("Source URL:", self.source_input)
        layout.addRow("Excerpt:", self.excerpt_input)
        layout.addRow("Treatment status:", self.treatment_input)
        layout.addRow("Notes:", self.notes_input)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self) -> None:
        self.data = {
            "authority_type": self.type_input.text().strip(),
            "title": self.title_input.text().strip(),
            "citation": self.citation_input.text().strip(),
            "jurisdiction": self.jurisdiction_input.text().strip(),
            "court": self.court_input.text().strip(),
            "year": int(self.year_input.text().strip()) if self.year_input.text().strip().isdigit() else None,
            "source_url": self.source_input.text().strip(),
            "source_text_excerpt": self.excerpt_input.toPlainText().strip(),
            "treatment_status": self.treatment_input.currentText(),
            "treatment_notes": self.notes_input.toPlainText().strip(),
            "verified": False,
        }
        self.accept()
