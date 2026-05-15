"""Structured logging configuration for the Litigation Expert AI System."""

import logging
import logging.handlers
import os
import tempfile
from pathlib import Path


def _resolve_console_log_level() -> int:
    level_name = (
        os.getenv("LEGAL_AGENT_CONSOLE_LOG_LEVEL")
        or os.getenv("LEGAL_AGENT_LOG_LEVEL")
        or os.getenv("LOG_LEVEL")
        or "WARNING"
    )
    return getattr(logging, level_name.strip().upper(), logging.WARNING)


def _resolve_file_log_level() -> int:
    level_name = (
        os.getenv("LEGAL_AGENT_FILE_LOG_LEVEL")
        or os.getenv("LEGAL_AGENT_LOG_LEVEL")
        or os.getenv("LOG_LEVEL")
        or "WARNING"
    )
    return getattr(logging, level_name.strip().upper(), logging.WARNING)


def _candidate_log_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.getenv("LEGAL_AGENT_LOG_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    candidates.extend(
        [
            Path.home() / ".legal_agent" / "logs",
            Path.cwd() / ".legal_agent" / "logs",
            Path(tempfile.gettempdir()) / "legal_agent" / "logs",
        ]
    )
    return candidates


class LoggerSetup:
    """Configure and manage structured logging for the application."""
    
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerSetup, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Initialize logging configuration."""
        logger = logging.getLogger("legal_agent")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers = []

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        log_file: Path | None = None
        for log_dir in _candidate_log_dirs():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                candidate = log_dir / "legal_agent.log"
                file_handler = logging.handlers.RotatingFileHandler(
                    candidate,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=5
                )
                file_handler.setLevel(_resolve_file_log_level())
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                log_file = candidate
                break
            except OSError:
                continue

        console_handler = logging.StreamHandler()
        console_handler.setLevel(_resolve_console_log_level())
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        LoggerSetup._logger = logger
        if log_file:
            logger.debug("Logging initialized. Log file: %s", log_file)
        else:
            logger.warning("Logging initialized without a writable log file.")
    
    @staticmethod
    def get_logger(name: str = "legal_agent") -> logging.Logger:
        """Get a logger instance."""
        if LoggerSetup._logger is None:
            LoggerSetup()
        return logging.getLogger(name)


# Convenience function
def get_logger(name: str = "legal_agent") -> logging.Logger:
    """Get a configured logger instance."""
    return LoggerSetup.get_logger(name)


# Initialize logging on module import
_setup = LoggerSetup()
