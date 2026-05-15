import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from .models import Case, Party, Fact, Claim, Evidence, ActionItem, Authority, ResearchLog, Document, VulnerabilityCheck, SettingsRecord, AuditLogRecord
from .logger import get_logger
from .observability import performance_checkpoint, record_db_connection, record_db_initialization, summarize_path

logger = get_logger(__name__)

DEFAULT_DB_PATH = Path.cwd() / "legal_agent.db"
_initialized_db_paths: set[str] = set()
_init_lock = threading.Lock()


class InstrumentedConnection(sqlite3.Connection):
    def commit(self) -> None:
        with performance_checkpoint(
            "database_write_commit",
            context={"db_path": getattr(self, "_legal_agent_db_path", "unknown")},
            slow_ms=200,
            log_success=False,
        ):
            return super().commit()


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH


def _db_path_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path)


def check_db_health(db_path: str | Path | None = None) -> bool:
    """Check if database is accessible and healthy."""
    path = _db_path(db_path)
    try:
        with performance_checkpoint(
            "database_health_check",
            context={"db_path": summarize_path(path)},
            slow_ms=500,
        ):
            with sqlite3.connect(str(path), timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.execute("PRAGMA quick_check")
                health = cursor.fetchone()
                if health and str(health[0]).lower() != "ok":
                    logger.error("Database quick_check failed for %s: %s", path, health[0])
                    return False
                logger.debug(f"Database health check passed: {path}")
                return True
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error during health check: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during database health check: {e}")
        return False


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Get a database connection with error handling."""
    path = _db_path(db_path)
    start = time.perf_counter()
    try:
        conn = sqlite3.connect(str(path), timeout=10.0, factory=InstrumentedConnection)
        try:
            conn._legal_agent_db_path = summarize_path(path)
        except AttributeError:
            pass
        conn.row_factory = sqlite3.Row
        record_db_connection(path, (time.perf_counter() - start) * 1000)
        return conn
    except sqlite3.OperationalError as e:
        record_db_connection(path, (time.perf_counter() - start) * 1000, success=False, exception_type=type(e).__name__)
        logger.error(f"Failed to connect to database: {e}")
        raise ValueError(f"Cannot access database: {str(e)[:100]}")
    except Exception as e:
        record_db_connection(path, (time.perf_counter() - start) * 1000, success=False, exception_type=type(e).__name__)
        logger.error(f"Unexpected error connecting to database: {e}")
        raise


def init_db(db_path: str | Path | None = None, *, force: bool = False) -> None:
    """Initialize database with all required tables."""
    path = _db_path(db_path)
    path_key = _db_path_key(path)
    with _init_lock:
        if not force and path_key in _initialized_db_paths and path.exists():
            record_db_initialization(path, skipped=True)
            logger.debug("Database initialization skipped; already initialized in this process: %s", path)
            return
        record_db_initialization(path)

    try:
        with performance_checkpoint(
            "database_initialization",
            context={"db_path": summarize_path(path), "force": force},
            slow_ms=1000,
        ):
            logger.debug("Initializing database: %s", path)
            with get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    legal_track TEXT,
                    jurisdiction TEXT,
                    court_name TEXT,
                    court_level TEXT,
                    district TEXT,
                    judge TEXT,
                    department TEXT,
                    filing_status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS parties (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    name TEXT,
                    role TEXT,
                    type TEXT,
                    notes TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    date TEXT,
                    fact_text TEXT,
                    source_evidence_id INTEGER,
                    relevance TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS claims (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    claim_name TEXT,
                    claim_type TEXT,
                    jurisdiction_basis TEXT,
                    required_elements_json TEXT,
                    status TEXT,
                    notes TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    title TEXT,
                    evidence_type TEXT,
                    description TEXT,
                    file_path TEXT,
                    date_obtained TEXT,
                    supports_claims_json TEXT,
                    admissibility_notes TEXT,
                    weakness_notes TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS action_items (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    action_text TEXT,
                    category TEXT,
                    due_date TEXT,
                    dependency TEXT,
                    status TEXT,
                    notes TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS authorities (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    authority_type TEXT,
                    title TEXT,
                    citation TEXT,
                    jurisdiction TEXT,
                    court TEXT,
                    year INTEGER,
                    source_url TEXT,
                    source_text_excerpt TEXT,
                    treatment_status TEXT,
                    treatment_notes TEXT,
                    verified INTEGER DEFAULT 0,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS research_logs (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    query TEXT,
                    source TEXT,
                    result_summary TEXT,
                    authority_ids_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    document_type TEXT,
                    title TEXT,
                    outline_json TEXT,
                    draft_markdown TEXT,
                    verification_status TEXT,
                    vulnerability_status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vulnerability_checks (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    document_id INTEGER,
                    issue_type TEXT,
                    risk_level TEXT,
                    description TEXT,
                    supporting_authority_id INTEGER,
                    recommended_fix TEXT,
                    resolved INTEGER DEFAULT 0,
                    FOREIGN KEY(case_id) REFERENCES cases(id),
                    FOREIGN KEY(document_id) REFERENCES documents(id),
                    FOREIGN KEY(supporting_authority_id) REFERENCES authorities(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    event_type TEXT,
                    description TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS safe_check_events (
                    id INTEGER PRIMARY KEY,
                    case_id INTEGER,
                    event_type TEXT,
                    severity TEXT,
                    source TEXT,
                    message TEXT,
                    details_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS safe_check_snapshots (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    case_id INTEGER,
                    view_name TEXT,
                    reason TEXT,
                    payload_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                )
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_safe_check_snapshots_case_created
                ON safe_check_snapshots(case_id, created_at DESC)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_safe_check_events_created
                ON safe_check_events(created_at DESC)
                """
                )
                conn.commit()
                with _init_lock:
                    _initialized_db_paths.add(path_key)
                logger.debug("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def _row_to_case(row: sqlite3.Row) -> Case:
    return Case(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        legal_track=row["legal_track"],
        jurisdiction=row["jurisdiction"],
        court_name=row["court_name"],
        court_level=row["court_level"],
        district=row["district"],
        judge=row["judge"],
        department=row["department"],
        filing_status=row["filing_status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"])
    )


def _row_to_party(row: sqlite3.Row) -> Party:
    return Party(
        id=row["id"],
        case_id=row["case_id"],
        name=row["name"],
        role=row["role"],
        type=row["type"],
        notes=row["notes"]
    )


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        id=row["id"],
        case_id=row["case_id"],
        date=row["date"],
        fact_text=row["fact_text"],
        source_evidence_id=row["source_evidence_id"],
        relevance=row["relevance"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


def _row_to_claim(row: sqlite3.Row) -> Claim:
    return Claim(
        id=row["id"],
        case_id=row["case_id"],
        claim_name=row["claim_name"],
        claim_type=row["claim_type"],
        jurisdiction_basis=row["jurisdiction_basis"],
        required_elements_json=row["required_elements_json"],
        status=row["status"],
        notes=row["notes"]
    )


def _row_to_evidence(row: sqlite3.Row) -> Evidence:
    return Evidence(
        id=row["id"],
        case_id=row["case_id"],
        title=row["title"],
        evidence_type=row["evidence_type"],
        description=row["description"],
        file_path=row["file_path"],
        date_obtained=row["date_obtained"],
        supports_claims_json=row["supports_claims_json"],
        admissibility_notes=row["admissibility_notes"],
        weakness_notes=row["weakness_notes"]
    )


def _row_to_action_item(row: sqlite3.Row) -> ActionItem:
    return ActionItem(
        id=row["id"],
        case_id=row["case_id"],
        action_text=row["action_text"],
        category=row["category"],
        due_date=row["due_date"],
        dependency=row["dependency"],
        status=row["status"],
        notes=row["notes"]
    )


def _row_to_authority(row: sqlite3.Row) -> Authority:
    return Authority(
        id=row["id"],
        case_id=row["case_id"],
        authority_type=row["authority_type"],
        title=row["title"],
        citation=row["citation"],
        jurisdiction=row["jurisdiction"],
        court=row["court"],
        year=row["year"],
        source_url=row["source_url"],
        source_text_excerpt=row["source_text_excerpt"],
        treatment_status=row["treatment_status"],
        treatment_notes=row["treatment_notes"],
        verified=bool(row["verified"]),
        created_at=datetime.fromisoformat(row["created_at"])
    )


def _row_to_research_log(row: sqlite3.Row) -> ResearchLog:
    return ResearchLog(
        id=row["id"],
        case_id=row["case_id"],
        query=row["query"],
        source=row["source"],
        result_summary=row["result_summary"],
        authority_ids_json=row["authority_ids_json"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        case_id=row["case_id"],
        document_type=row["document_type"],
        title=row["title"],
        outline_json=row["outline_json"],
        draft_markdown=row["draft_markdown"],
        verification_status=row["verification_status"],
        vulnerability_status=row["vulnerability_status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"])
    )


def _row_to_vulnerability_check(row: sqlite3.Row) -> VulnerabilityCheck:
    return VulnerabilityCheck(
        id=row["id"],
        case_id=row["case_id"],
        document_id=row["document_id"],
        issue_type=row["issue_type"],
        risk_level=row["risk_level"],
        description=row["description"],
        supporting_authority_id=row["supporting_authority_id"],
        recommended_fix=row["recommended_fix"],
        resolved=bool(row["resolved"])
    )


def _row_to_audit_log(row: sqlite3.Row) -> AuditLogRecord:
    return AuditLogRecord(
        id=row["id"],
        case_id=row["case_id"],
        event_type=row["event_type"],
        description=row["description"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


def get_setting(key: str, db_path: str | Path | None = None) -> Optional[str]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def save_setting(key: str, value: str, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def log_audit_event(case_id: Optional[int], event_type: str, description: str, created_at: str, db_path: str | Path | None = None) -> int:
    event_type = event_type.strip() if isinstance(event_type, str) else ""
    description = description.strip() if isinstance(description, str) else ""
    created_at = created_at.strip() if isinstance(created_at, str) else ""
    if not event_type:
        event_type = "manual"
    if not description:
        description = "Untitled audit event"
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (case_id, event_type, description, created_at) VALUES (?, ?, ?, ?)",
            (case_id, event_type, description, created_at),
        )
        conn.commit()
        return cursor.lastrowid


def get_audit_events(limit: int = 50, db_path: str | Path | None = None) -> List[AuditLogRecord]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_row_to_audit_log(row) for row in cursor.fetchall()] 


def record_safe_check_event(
    event_type: str,
    severity: str,
    source: str,
    message: str,
    details: dict | None = None,
    case_id: Optional[int] = None,
    db_path: str | Path | None = None,
) -> int:
    event_type = event_type.strip() if isinstance(event_type, str) else ""
    severity = severity.strip().lower() if isinstance(severity, str) else ""
    source = source.strip() if isinstance(source, str) else ""
    message = message.strip() if isinstance(message, str) else ""
    if not event_type:
        event_type = "safe_check_event"
    if severity not in {"info", "warning", "error", "critical"}:
        severity = "info"
    if not source:
        source = "safe_check"
    if not message:
        message = "Safe check event recorded."
    details_json = json.dumps(details or {}, sort_keys=True)
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO safe_check_events
            (case_id, event_type, severity, source, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, event_type, severity, source, message, details_json, created_at),
        )
        event_id = cursor.lastrowid
        if case_id is not None and severity in {"warning", "error", "critical"}:
            cursor.execute(
                "INSERT INTO audit_logs (case_id, event_type, description, created_at) VALUES (?, ?, ?, ?)",
                (case_id, f"safe_check:{event_type}", message, created_at),
            )
        conn.commit()
        return event_id


def get_safe_check_events(limit: int = 100, db_path: str | Path | None = None) -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM safe_check_events ORDER BY created_at DESC LIMIT ?", (limit,))
        events = []
        for row in cursor.fetchall():
            try:
                details = json.loads(row["details_json"] or "{}")
            except json.JSONDecodeError:
                details = {}
            events.append(
                {
                    "id": row["id"],
                    "case_id": row["case_id"],
                    "event_type": row["event_type"],
                    "severity": row["severity"],
                    "source": row["source"],
                    "message": row["message"],
                    "details": details,
                    "created_at": row["created_at"],
                }
            )
        return events


def save_safe_check_snapshot(
    session_id: str,
    payload: dict,
    reason: str = "autosave",
    case_id: Optional[int] = None,
    view_name: str = "",
    db_path: str | Path | None = None,
) -> int:
    session_id = session_id.strip() if isinstance(session_id, str) else ""
    reason = reason.strip() if isinstance(reason, str) else ""
    view_name = view_name.strip() if isinstance(view_name, str) else ""
    if not session_id:
        session_id = "unknown-session"
    if not reason:
        reason = "autosave"
    payload_json = json.dumps(payload, sort_keys=True)
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO safe_check_snapshots
            (session_id, case_id, view_name, reason, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, case_id, view_name, reason, payload_json, created_at),
        )
        conn.commit()
        return cursor.lastrowid


def get_safe_check_snapshots(
    case_id: Optional[int] = None,
    limit: int = 20,
    db_path: str | Path | None = None,
) -> list[dict]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if case_id is None:
            cursor.execute("SELECT * FROM safe_check_snapshots ORDER BY created_at DESC LIMIT ?", (limit,))
        else:
            cursor.execute(
                "SELECT * FROM safe_check_snapshots WHERE case_id = ? ORDER BY created_at DESC LIMIT ?",
                (case_id, limit),
            )
        snapshots = []
        for row in cursor.fetchall():
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            snapshots.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "case_id": row["case_id"],
                    "view_name": row["view_name"],
                    "reason": row["reason"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return snapshots
