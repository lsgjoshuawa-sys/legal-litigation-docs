from __future__ import annotations

import json
import re
from typing import Any


def items_from_text(value: str | None) -> list[str]:
    """Return list items from plain lines, comma text, or a legacy JSON list."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return []
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if parsed is not None:
        parsed_text = str(parsed).strip()
        return [parsed_text] if parsed_text else []

    separators = r"[\n,]+"
    return [item.strip(" \t\r-*\u2022") for item in re.split(separators, text) if item.strip(" \t\r-*\u2022")]


def plain_text_from_list_storage(value: str | None) -> str:
    return "\n".join(items_from_text(value))


def json_list_from_plain_text(value: str | None) -> str:
    return json.dumps(items_from_text(value))


def json_list_from_identifier_text(value: str | None) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return "[]"
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps([item.strip() for item in re.split(r"[\s,]+", text) if item.strip()])
    if isinstance(parsed, list):
        return json.dumps([str(item).strip() for item in parsed if str(item).strip()])
    parsed_text = str(parsed).strip()
    return json.dumps([parsed_text] if parsed_text else [])
