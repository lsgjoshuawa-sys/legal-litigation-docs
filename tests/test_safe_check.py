import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEGAL_AGENT_SAFE_CHECK_DISABLED", "1")

from PySide6 import QtWidgets

from legal_agent import db, safe_check
from legal_agent_gui.audit_log_view import AuditLogView
from legal_agent_gui.main_window import MainWindow
from legal_agent_gui.session_safety import GuiSafeCheckSupervisor


class SafeCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_safe_check_dir = tempfile.TemporaryDirectory()
        self.previous_safe_check_dir = os.environ.get("LEGAL_AGENT_SAFE_CHECK_DIR")
        os.environ["LEGAL_AGENT_SAFE_CHECK_DIR"] = self.temp_safe_check_dir.name
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)
        if self.previous_safe_check_dir is None:
            os.environ.pop("LEGAL_AGENT_SAFE_CHECK_DIR", None)
        else:
            os.environ["LEGAL_AGENT_SAFE_CHECK_DIR"] = self.previous_safe_check_dir
        self.temp_safe_check_dir.cleanup()

    def test_safe_check_event_and_snapshot_round_trip(self):
        event_id = db.record_safe_check_event(
            "slow_snapshot",
            "warning",
            "test",
            "Snapshot was slow.",
            {"elapsed_seconds": 1.25},
            db_path=self.temp_db.name,
        )
        snapshot_id = db.save_safe_check_snapshot(
            "session-1",
            {"fields": {"Case Intake": {"title_input": "Draft title"}}},
            reason="autosave",
            view_name="Case Intake",
            db_path=self.temp_db.name,
        )

        self.assertGreater(event_id, 0)
        self.assertGreater(snapshot_id, 0)
        self.assertEqual(db.get_safe_check_events(db_path=self.temp_db.name)[0]["event_type"], "slow_snapshot")
        self.assertEqual(
            db.get_safe_check_snapshots(db_path=self.temp_db.name)[0]["payload"]["fields"]["Case Intake"]["title_input"],
            "Draft title",
        )

    def test_gui_snapshot_captures_unsaved_fields_and_skips_settings(self):
        window = MainWindow(db_path=self.temp_db.name)
        supervisor = GuiSafeCheckSupervisor(window, self.temp_db.name)

        window.views["Case Intake"].title_input.setText("Unsaved emergency draft")
        window.views["Settings"].api_key_input.setText("sk-test-secret")
        snapshot = supervisor.collect_snapshot("test")

        self.assertEqual(
            snapshot["fields"]["Case Intake"]["title_input"],
            "Unsaved emergency draft",
        )
        self.assertNotIn("Settings", snapshot["fields"])

    def test_gui_snapshot_ignores_default_only_content_for_database_storage(self):
        window = MainWindow(db_path=self.temp_db.name)
        supervisor = GuiSafeCheckSupervisor(window, self.temp_db.name)

        supervisor.capture_snapshot("startup")

        self.assertEqual(db.get_safe_check_snapshots(db_path=self.temp_db.name), [])

    def test_non_actionable_info_event_is_suppressed(self):
        event_id = safe_check.record_event(
            "watchdog_closed",
            "info",
            "test",
            "Normal close should not clutter diagnostics.",
            db_path=self.temp_db.name,
        )

        self.assertEqual(event_id, 0)
        self.assertEqual(db.get_safe_check_events(db_path=self.temp_db.name), [])

    def test_diagnostic_start_prunes_oldest_session_log_set(self):
        root = Path(self.temp_safe_check_dir.name)
        base_time = 1_700_000_000
        for index in range(3):
            session_id = f"session-{index}"
            files = [
                root / f"{session_id}.diagnostic.jsonl",
                root / f"{session_id}.heartbeat.json",
                root / f"{session_id}.snapshot.json",
                root / f"{session_id}.fatal.log",
            ]
            files[0].write_text("{}\n", encoding="utf-8")
            safe_check.atomic_write_json(files[1], {"session_id": session_id, "status": "closed", "pid": 0})
            safe_check.atomic_write_json(files[2], {"session_id": session_id, "fields": {}})
            files[3].write_text("", encoding="utf-8")
            for path in files:
                os.utime(path, (base_time + index, base_time + index))

        safe_check.append_diagnostic_report("session-3", "diagnostic_report_started", {})

        self.assertFalse((root / "session-0.diagnostic.jsonl").exists())
        self.assertFalse((root / "session-0.heartbeat.json").exists())
        self.assertFalse((root / "session-0.snapshot.json").exists())
        self.assertFalse((root / "session-0.fatal.log").exists())
        for session_id in ("session-1", "session-2", "session-3"):
            self.assertTrue((root / f"{session_id}.diagnostic.jsonl").exists())

    def test_audit_log_safe_check_items_expose_improvement_details(self):
        db.record_safe_check_event(
            "heartbeat_stale",
            "warning",
            "test",
            "Heartbeat became stale.",
            {"improvement_hint": "Inspect slow refresh in Evidence view.", "elapsed_seconds": 18.4},
            db_path=self.temp_db.name,
        )
        view = AuditLogView(db_path=self.temp_db.name)
        view.refresh()

        item = view.safe_check_list.item(0)
        self.assertIn("Hint: Inspect slow refresh in Evidence view.", item.text())
        self.assertIn('"elapsed_seconds": 18.4', item.toolTip())

    def test_watchdog_records_crash_when_gui_pid_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            heartbeat_path = Path(temp_dir) / "heartbeat.json"
            snapshot_path = Path(temp_dir) / "snapshot.json"
            safe_check.atomic_write_json(
                heartbeat_path,
                {"session_id": "session-2", "pid": 999999999, "case_id": None, "status": "running"},
            )
            safe_check.atomic_write_json(
                snapshot_path,
                {"session_id": "session-2", "current_view": "Case Intake", "fields": {"Case Intake": {}}},
            )

            exit_code = safe_check.watch_gui(
                session_id="session-2",
                pid=999999999,
                db_path=self.temp_db.name,
                heartbeat_path=heartbeat_path,
                snapshot_path=snapshot_path,
                interval_seconds=0.5,
                stale_seconds=3.0,
            )

        self.assertEqual(exit_code, 2)
        events = db.get_safe_check_events(db_path=self.temp_db.name)
        self.assertEqual(events[0]["event_type"], "gui_crash_or_forced_exit")


if __name__ == "__main__":
    unittest.main()
