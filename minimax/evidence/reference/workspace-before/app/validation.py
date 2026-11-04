"""Input validation shared by the HTTP layer and the store."""

from __future__ import annotations

from datetime import date
from typing import Any


class ValidationError(ValueError):
    """A caller-visible invalid argument (HTTP 400)."""

    code = "invalid_argument"

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class NotFoundError(ValidationError):
    """A caller-visible missing resource (HTTP 404)."""

    code = "not_found"


STATUSES = ("todo", "in_progress", "done")
PRIORITIES = ("low", "medium", "high")


def require_title(payload: dict[str, Any]) -> str:
    value = payload.get("title")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("title is required and must be a non-empty string", "title")
    title = value.strip()
    if len(title) > 200:
        raise ValidationError("title must be at most 200 characters", "title")
    return title


def parse_status(value: Any, field: str = "status") -> str:
    if value not in STATUSES:
        raise ValidationError(f"{field} must be one of {', '.join(STATUSES)}", field)
    return str(value)


def parse_priority(value: Any, field: str = "priority") -> str:
    if value not in PRIORITIES:
        raise ValidationError(f"{field} must be one of {', '.join(PRIORITIES)}", field)
    return str(value)


def parse_optional_text(value: Any, field: str, max_len: int = 200) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string or null", field)
    text = value.strip()
    if len(text) > max_len:
        raise ValidationError(f"{field} must be at most {max_len} characters", field)
    return text or None


def parse_date(value: Any, field: str = "due_date") -> str | None:
    """Parse a strict ISO date (YYYY-MM-DD) into its canonical text form."""

    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a YYYY-MM-DD string or null", field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be a valid YYYY-MM-DD date", field) from exc
    if parsed.isoformat() != value:
        raise ValidationError(f"{field} must be a valid YYYY-MM-DD date", field)
    return parsed.isoformat()


def parse_int(
    value: Any,
    field: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an integer", field) from exc
    if parsed < minimum or parsed > maximum:
        raise ValidationError(f"{field} must be between {minimum} and {maximum}", field)
    return parsed
