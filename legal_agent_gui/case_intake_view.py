from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.case_tracks import LEGAL_TRACK_CHOICES, normalize_legal_track, purpose_for_track
from legal_agent.intake import create_case, get_case, list_cases, update_case
from .widgets import BaseView


class CaseIntakeView(BaseView):
    def __init__(self, db_path: str | None = None, main_window: QtWidgets.QWidget | None = None) -> None:
        super().__init__("Case Intake", "Create or edit case intake details and jurisdictional information.")
        self.db_path = db_path
        self.main_window = main_window
        self.case_id: int | None = None
        self.form = QtWidgets.QFormLayout()
        self.title_input = QtWidgets.QLineEdit()
        self.description_input = QtWidgets.QTextEdit()
        self.track_input = QtWidgets.QComboBox()
        self.track_input.addItems(LEGAL_TRACK_CHOICES)
        self.track_input.currentTextChanged.connect(self._update_track_purpose)
        self.track_purpose_label = QtWidgets.QLabel("")
        self.track_purpose_label.setWordWrap(True)
        self.court_input = QtWidgets.QLineEdit()
        self.jurisdiction_input = QtWidgets.QComboBox()
        self.jurisdiction_input.addItems(["", "California Superior Court", "Federal Eastern District of California", "Local law enforcement / local government civil dispute", "Mixed / unclear"])
        self.judge_input = QtWidgets.QLineEdit()
        self.department_input = QtWidgets.QLineEdit()
        self.filing_status_input = QtWidgets.QLineEdit()
        self.save_button = QtWidgets.QPushButton("Save Case")
        self.save_button.clicked.connect(self._save_case)
        self.form.addRow("Title:", self.title_input)
        self.form.addRow("Description:", self.description_input)
        self.form.addRow("Procedure track:", self.track_input)
        self.form.addRow("Track purpose:", self.track_purpose_label)
        self.form.addRow("Court name:", self.court_input)
        self.form.addRow("Jurisdiction:", self.jurisdiction_input)
        self.form.addRow("Judge:", self.judge_input)
        self.form.addRow("Department:", self.department_input)
        self.form.addRow("Filing status:", self.filing_status_input)
        self.layout.addLayout(self.form)
        self.layout.addWidget(self.save_button)
        self.warning_label = QtWidgets.QLabel("")
        self.layout.addWidget(self.warning_label)
        self._update_track_purpose("")

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _save_case(self) -> None:
        title = self.title_input.text().strip()
        if self.case_id:
            update_case(
                self.case_id,
                title,
                self.description_input.toPlainText().strip(),
                normalize_legal_track(self.track_input.currentText()),
                self.jurisdiction_input.currentText(),
                self.court_input.text().strip(),
                "",
                "",
                self.judge_input.text().strip(),
                self.department_input.text().strip(),
                self.filing_status_input.text().strip(),
                self.db_path,
            )
        else:
            self.case_id = create_case(
                title=title,
                description=self.description_input.toPlainText().strip(),
                legal_track=normalize_legal_track(self.track_input.currentText()),
                jurisdiction=self.jurisdiction_input.currentText(),
                court_name=self.court_input.text().strip(),
                judge=self.judge_input.text().strip(),
                department=self.department_input.text().strip(),
                filing_status=self.filing_status_input.text().strip(),
                db_path=self.db_path,
            )
        self.warning_label.setText("Case saved.")
        self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        if not self.case_id:
            self.title_input.clear()
            self.description_input.clear()
            self.track_input.setCurrentIndex(0)
            self._update_track_purpose("")
            self.court_input.clear()
            self.jurisdiction_input.setCurrentIndex(0)
            self.judge_input.clear()
            self.department_input.clear()
            self.filing_status_input.clear()
            return
        case = get_case(self.case_id, self.db_path)
        if not case:
            return
        self.title_input.setText(case.title)
        self.description_input.setPlainText(case.description)
        self.track_input.setCurrentText(normalize_legal_track(case.legal_track))
        self._update_track_purpose(self.track_input.currentText())
        self.court_input.setText(case.court_name)
        self.jurisdiction_input.setCurrentText(case.jurisdiction)
        self.judge_input.setText(case.judge)
        self.department_input.setText(case.department)
        self.filing_status_input.setText(case.filing_status)

    def _update_track_purpose(self, track: str) -> None:
        purpose = purpose_for_track(track)
        self.track_purpose_label.setText(purpose or "Select the procedure track that best describes how this matter should be handled.")
