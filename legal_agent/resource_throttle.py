from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterator

from .logger import get_logger

logger = get_logger(__name__)


def _load_dotenv(env_path: str | Path | None = None) -> None:
    path = Path(env_path) if env_path else Path.cwd() / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Unable to read .env for throttle settings: %s", exc)
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class ResourceBudget:
    enabled: bool = True
    ai_requests_per_minute: int = 6
    ai_max_concurrent_requests: int = 1
    ai_max_context_chars: int = 12000
    ai_max_output_tokens: int = 800
    http_requests_per_minute: int = 30
    http_max_concurrent_requests: int = 2
    citation_checks_per_run: int = 8
    max_wait_seconds: int = 30

    @classmethod
    def from_env(cls) -> "ResourceBudget":
        _load_dotenv()
        legacy_ai_limit = os.getenv("LEGAL_AGENT_OPENAI_MAX_REQUESTS_PER_MINUTE")
        ai_limit_default = int(legacy_ai_limit) if legacy_ai_limit and legacy_ai_limit.isdigit() else 6
        return cls(
            enabled=_env_bool("LEGAL_AGENT_THROTTLE_ENABLED", True),
            ai_requests_per_minute=_env_int("LEGAL_AGENT_AI_MAX_REQUESTS_PER_MINUTE", ai_limit_default),
            ai_max_concurrent_requests=_env_int("LEGAL_AGENT_AI_MAX_CONCURRENT_REQUESTS", 1),
            ai_max_context_chars=_env_int("LEGAL_AGENT_AI_MAX_CONTEXT_CHARS", 12000, minimum=1000),
            ai_max_output_tokens=_env_int("LEGAL_AGENT_AI_MAX_OUTPUT_TOKENS", 800, minimum=128),
            http_requests_per_minute=_env_int("LEGAL_AGENT_HTTP_MAX_REQUESTS_PER_MINUTE", 30),
            http_max_concurrent_requests=_env_int("LEGAL_AGENT_HTTP_MAX_CONCURRENT_REQUESTS", 2),
            citation_checks_per_run=_env_int("LEGAL_AGENT_CITATION_CHECKS_PER_RUN", 8),
            max_wait_seconds=_env_int("LEGAL_AGENT_THROTTLE_MAX_WAIT_SECONDS", 30),
        )


class ThrottleExceeded(ValueError):
    """Raised when an operation would exceed the configured resource budget."""


class ThrottlingAgent:
    """Application-wide throttle for AI, HTTP, context, and citation-validation work."""

    def __init__(
        self,
        budget: ResourceBudget | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.budget = budget or ResourceBudget.from_env()
        self._sleeper = sleeper
        self._clock = clock
        self._lock = threading.Lock()
        self._timestamps: dict[str, list[float]] = {"ai": [], "http": []}
        self._semaphores = {
            "ai": threading.BoundedSemaphore(self.budget.ai_max_concurrent_requests),
            "http": threading.BoundedSemaphore(self.budget.http_max_concurrent_requests),
        }

    @contextmanager
    def gate(self, operation: str, metadata: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        operation = operation if operation in {"ai", "http"} else "http"
        if not self.budget.enabled:
            yield {"operation": operation, "throttled": False, "wait_seconds": 0.0, "metadata": metadata or {}}
            return

        semaphore = self._semaphores[operation]
        acquired = semaphore.acquire(timeout=self.budget.max_wait_seconds)
        if not acquired:
            raise ThrottleExceeded(f"{operation.upper()} work is already at its concurrency limit.")
        try:
            wait_seconds = self._reserve_slot(operation)
            yield {
                "operation": operation,
                "throttled": True,
                "wait_seconds": wait_seconds,
                "metadata": metadata or {},
            }
        finally:
            semaphore.release()

    def clamp_ai_context(self, context: str) -> tuple[str, dict[str, Any]]:
        original_length = len(context or "")
        clamped = self._trim_middle(context or "", self.budget.ai_max_context_chars)
        return clamped, {
            "original_chars": original_length,
            "sent_chars": len(clamped),
            "truncated": len(clamped) < original_length,
            "limit_chars": self.budget.ai_max_context_chars,
        }

    def clamp_ai_output_tokens(self, requested_tokens: int) -> int:
        return min(max(1, requested_tokens), self.budget.ai_max_output_tokens)

    def add_ai_procedure(self, instructions: str, context_status: dict[str, Any]) -> str:
        procedure = (
            "\n\nMandatory resource throttling procedure:\n"
            f"- Application throttle enabled: {self.budget.enabled}.\n"
            f"- AI calls are limited to {self.budget.ai_requests_per_minute} per minute and "
            f"{self.budget.ai_max_concurrent_requests} concurrent request(s).\n"
            f"- Case profile context is capped at {self.budget.ai_max_context_chars} characters; "
            f"current payload sent {context_status['sent_chars']} of {context_status['original_chars']} characters.\n"
            f"- Response budget is capped at {self.budget.ai_max_output_tokens} output tokens.\n"
            "- Follow the supplied context only. If the context was truncated, state that further review may require a refreshed or narrower query.\n"
        )
        return f"{instructions.rstrip()}{procedure}"

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "budget": asdict(self.budget),
                "recent": {key: len(self._recent(value)) for key, value in self._timestamps.items()},
            }

    def _reserve_slot(self, operation: str) -> float:
        limit = self.budget.ai_requests_per_minute if operation == "ai" else self.budget.http_requests_per_minute
        total_wait = 0.0
        while True:
            with self._lock:
                now = self._clock()
                timestamps = self._recent(self._timestamps[operation], now)
                self._timestamps[operation] = timestamps
                if len(timestamps) < limit:
                    timestamps.append(now)
                    return total_wait
                wait_seconds = max(0.0, 60.0 - (now - timestamps[0]))
            if total_wait + wait_seconds > self.budget.max_wait_seconds:
                raise ThrottleExceeded(
                    f"{operation.upper()} work is throttled. Retry after approximately {wait_seconds:.1f} seconds."
                )
            logger.warning(
                "Throttling %s work for %.1fs; consider lowering concurrency or narrowing requests.",
                operation,
                wait_seconds,
            )
            self._sleeper(wait_seconds)
            total_wait += wait_seconds

    def _recent(self, timestamps: list[float], now: float | None = None) -> list[float]:
        current = self._clock() if now is None else now
        return [timestamp for timestamp in timestamps if current - timestamp < 60.0]

    def _trim_middle(self, value: str, max_chars: int) -> str:
        if len(value) <= max_chars:
            return value
        marker = "\n\n[...content omitted by application throttle; use a narrower query or refresh if needed...]\n\n"
        if max_chars <= len(marker) + 20:
            return value[:max_chars]
        head_length = int((max_chars - len(marker)) * 0.7)
        tail_length = max_chars - len(marker) - head_length
        return f"{value[:head_length]}{marker}{value[-tail_length:]}"


_AGENT: ThrottlingAgent | None = None


def get_throttling_agent() -> ThrottlingAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = ThrottlingAgent()
    return _AGENT


def reset_throttling_agent(agent: ThrottlingAgent | None = None) -> None:
    global _AGENT
    _AGENT = agent
