from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

from .db import get_connection
from .logger import get_logger
from .observability import performance_checkpoint, record_openai_client_initialization
from .resource_throttle import get_throttling_agent
from .verification import build_openai_prompt

logger = get_logger(__name__)

CONFIG_FILE = Path(os.getenv("LEGAL_AGENT_CONFIG_FILE", Path.home() / ".legal_agent_settings.json"))
DEFAULT_MODEL = os.getenv("LEGAL_AGENT_OPENAI_MODEL", "gpt-4o-mini")
ENV_VAR_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _configured_rate_limit() -> int:
    try:
        return max(1, int(os.getenv("LEGAL_AGENT_OPENAI_MAX_REQUESTS_PER_MINUTE", "20")))
    except ValueError:
        return 20


MAX_REQUESTS_PER_MINUTE = _configured_rate_limit()
_request_times: list[float] = []
_rate_limit_lock = threading.Lock()
_client_cache: dict[tuple[int, str, str], Any] = {}
_client_lock = threading.Lock()


def load_dotenv(env_path: str | Path | None = None) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from .env without adding a runtime dependency."""
    path = Path(env_path) if env_path else Path.cwd() / ".env"
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Failed to read environment file %s: %s", path, exc)
        return loaded

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not ENV_VAR_PATTERN.match(key):
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
        loaded[key] = value
    return loaded


def _check_rate_limit() -> None:
    """Enforce a local per-process rate limit for API calls."""
    global _request_times
    with _rate_limit_lock:
        now = time.time()
        _request_times = [timestamp for timestamp in _request_times if now - timestamp < 60]

        if len(_request_times) >= MAX_REQUESTS_PER_MINUTE:
            wait_time = 60 - (now - _request_times[0])
            if wait_time > 0:
                logger.warning("OpenAI rate limit reached. Waiting %.1fs", wait_time)
                time.sleep(wait_time)
                now = time.time()
                _request_times = [timestamp for timestamp in _request_times if now - timestamp < 60]

        _request_times.append(time.time())


def _normalize_api_key(api_key: str) -> str:
    if not isinstance(api_key, str):
        raise ValueError("OpenAI API key must be text.")
    cleaned = api_key.strip()
    if not cleaned:
        raise ValueError("OpenAI API key is required.")
    if any(char.isspace() for char in cleaned):
        raise ValueError("OpenAI API key cannot contain whitespace.")
    return cleaned


class ConfigManager:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or CONFIG_FILE
        self.data = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            raw = self.config_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (OSError, ValueError) as exc:
            logger.warning("Failed to load config: %s", exc)
            return {}

    def _save_config(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            logger.debug("Config saved to %s", self.config_path)
        except OSError as exc:
            logger.error("Failed to save config: %s", exc)

    def set_api_key(self, api_key: str) -> None:
        cleaned = _normalize_api_key(api_key)
        encoded = base64.b64encode(cleaned.encode("utf-8")).decode("utf-8")
        self.data["openai_api_key"] = encoded
        self._save_config()
        logger.debug("API key saved to config")

    def get_api_key(self) -> str | None:
        load_dotenv()
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            logger.debug("Using API key from environment variable")
            return _normalize_api_key(env_key)

        encoded = self.data.get("openai_api_key")
        if not encoded:
            logger.debug("No API key found in config or environment")
            return None
        try:
            return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
        except (ValueError, TypeError) as exc:
            logger.error("Failed to decode API key: %s", exc)
            return None

    def has_api_key(self) -> bool:
        return bool(self.get_api_key())

    def set_setting(self, key: str, value: Any) -> None:
        self.data[key] = value
        self._save_config()
        logger.debug("Setting '%s' saved", key)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


def _get_client(api_key: str) -> Any:
    cleaned = _normalize_api_key(api_key)
    if openai is None:
        logger.error("openai package is not installed")
        raise ValueError("openai package is not installed")
    sdk = "modern" if hasattr(openai, "OpenAI") else "legacy"
    key_fingerprint = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]
    cache_key = (id(openai), sdk, key_fingerprint)
    with _client_lock:
        cached = _client_cache.get(cache_key)
    if cached is not None:
        record_openai_client_initialization(sdk=sdk, created=False)
        return cached

    with performance_checkpoint(
        "openai_client_initialization",
        context={"sdk": sdk, "api_key_fingerprint": key_fingerprint},
        slow_ms=500,
    ):
        if sdk == "modern":
            client = openai.OpenAI(api_key=cleaned)
        else:
            openai.api_key = cleaned
            client = openai
    with _client_lock:
        _client_cache[cache_key] = client
    record_openai_client_initialization(sdk=sdk, created=True)
    logger.debug("OpenAI client initialized with %s SDK", sdk)
    return client


def _create_chat_completion(client: Any, messages: list[dict[str, str]], max_tokens: int) -> Any:
    if hasattr(client, "chat") and hasattr(client.chat, "completions"):
        return client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=max_tokens,
        )
    return client.ChatCompletion.create(
        model=DEFAULT_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=max_tokens,
    )


def _response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", {})
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return str(content or "").strip()


def _raise_user_facing_error(exc: Exception, action: str) -> None:
    if isinstance(exc, ValueError):
        raise exc

    if openai is not None:
        error_map = [
            ("RateLimitError", "API rate limit exceeded. Please try again in a moment."),
            ("AuthenticationError", "OpenAI API authentication failed. Check your API key."),
            ("APIConnectionError", "Unable to reach the OpenAI API. Check the network connection."),
            ("APITimeoutError", "The OpenAI API request timed out. Please try again."),
            ("APIError", "OpenAI API error. Please try again or review the logs."),
        ]
        for error_name, message in error_map:
            error_type = getattr(openai, error_name, None)
            if error_type and isinstance(exc, error_type):
                logger.warning("%s during %s: %s", error_name, action, exc)
                raise ValueError(message) from exc

    logger.exception("Unexpected error during %s", action)
    raise ValueError(f"Unable to complete {action}. See application logs for details.") from exc


def _chat_completion(
    api_key: str,
    context: str,
    instructions: str,
    system_message: str,
    max_tokens: int,
    action: str,
) -> str:
    try:
        throttling_agent = get_throttling_agent()
        context, context_status = throttling_agent.clamp_ai_context(context)
        instructions = throttling_agent.add_ai_procedure(instructions, context_status)
        max_tokens = throttling_agent.clamp_ai_output_tokens(max_tokens)
        client = _get_client(api_key)
        prompt = build_openai_prompt(context, instructions)
        logger.debug("Requesting %s from OpenAI", action)
        with throttling_agent.gate("ai", metadata={"action": action, "prompt_chars": len(prompt)}):
            _check_rate_limit()
            with performance_checkpoint(
                "openai_ai_request",
                context={
                    "action": action,
                    "model": DEFAULT_MODEL,
                    "input_size_chars": len(prompt),
                    "max_output_units": max_tokens,
                },
                slow_ms=15_000,
            ):
                response = _create_chat_completion(
                    client,
                    [
                        {"role": "system", "content": f"{system_message} Obey the mandatory resource throttling procedure in the user prompt."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                )
        result = _response_text(response)
        if not result:
            raise ValueError("OpenAI returned an empty response.")
        logger.debug("OpenAI %s completed successfully", action)
        return result
    except Exception as exc:
        _raise_user_facing_error(exc, action)
        raise


def summarize_facts(api_key: str, facts: str, instructions: str = "Summarize factual points only.") -> str:
    """Summarize facts with user-facing API errors and local rate limiting."""
    return _chat_completion(
        api_key=api_key,
        context=facts,
        instructions=instructions,
        system_message="Provide conservative summaries only. Do not invent authorities.",
        max_tokens=400,
        action="fact summarization",
    )


def generate_draft(api_key: str, context: str, template: str) -> str:
    """Generate draft text with user-facing API errors and local rate limiting."""
    return _chat_completion(
        api_key=api_key,
        context=context,
        instructions=template,
        system_message="Generate draft text using only verified authorities and provided facts.",
        max_tokens=1200,
        action="draft generation",
    )


def analyze_text(api_key: str, context: str, question: str) -> str:
    """Analyze text with user-facing API errors and local rate limiting."""
    return _chat_completion(
        api_key=api_key,
        context=context,
        instructions=question,
        system_message="Analyze risks conservatively. Do not create any new legal authorities.",
        max_tokens=800,
        action="text analysis",
    )


def get_stored_api_key(db_path: str | None = None) -> str | None:
    """Get stored API key from database, environment, or config file."""
    try:
        with performance_checkpoint(
            "openai_api_key_lookup",
            context={"db_configured": bool(db_path)},
            slow_ms=250,
        ):
            if db_path:
                with get_connection(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM settings WHERE key = ?", ("openai_api_key",))
                    row = cursor.fetchone()
                    if row:
                        logger.debug("API key retrieved from database")
                        return base64.b64decode(row["value"].encode("utf-8")).decode("utf-8")
            api_key = ConfigManager().get_api_key()
            if api_key:
                logger.debug("API key retrieved from config or environment")
            return api_key
    except Exception as exc:
        logger.error("Error retrieving API key: %s", exc)
        return None


def save_api_key(api_key: str, db_path: str | None = None) -> None:
    """Save API key to database or config file."""
    cleaned = _normalize_api_key(api_key)
    try:
        with performance_checkpoint(
            "openai_api_key_save",
            context={"target": "database" if db_path else "config_file"},
            slow_ms=500,
        ):
            if db_path:
                encoded = base64.b64encode(cleaned.encode("utf-8")).decode("utf-8")
                with get_connection(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
                    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("openai_api_key", encoded))
                    conn.commit()
                logger.debug("API key saved to database")
            else:
                ConfigManager().set_api_key(cleaned)
                logger.debug("API key saved to config file")
    except Exception as exc:
        logger.error("Error saving API key: %s", exc)
        raise ValueError("Unable to save API key. See application logs for details.") from exc
