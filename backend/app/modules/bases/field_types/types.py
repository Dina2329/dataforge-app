from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine

from app.core.errors import ValidationError
from app.modules.bases.field_types.registry import BaseFieldType, register_field_type


@register_field_type("text")
class TextFieldType(BaseFieldType):
    key = "text"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return String(255)

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        return None if value is None else str(value)


@register_field_type("long_text")
class LongTextFieldType(BaseFieldType):
    key = "long_text"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return Text()

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        return None if value is None else str(value)


@register_field_type("number")
class NumberFieldType(BaseFieldType):
    key = "number"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return Numeric()

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"'{value}' is not a valid number") from exc

    def from_storage(self, raw: Any, options: dict[str, Any]) -> Any:
        # Postgres NUMERIC deserializes as Decimal, which Pydantic renders as a
        # quoted string in JSON by default — coerce to float for a real JSON number.
        return None if raw is None else float(raw)


@register_field_type("boolean")
class BooleanFieldType(BaseFieldType):
    key = "boolean"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return Boolean()

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            # bool("false") is True in Python — string forms (from CSV import,
            # form fields, etc.) need explicit parsing, not a truthiness check.
            normalized = value.strip().lower()
            if normalized in ("true", "1", "yes"):
                return True
            if normalized in ("false", "0", "no", ""):
                return False
            raise ValidationError(f"'{value}' is not a valid boolean")
        return bool(value)


@register_field_type("date")
class DateFieldType(BaseFieldType):
    key = "date"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return Date()

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value
        # date.fromisoformat() only accepts a bare "YYYY-MM-DD" -- it raises
        # on any full timestamp string (e.g. Elasticsearch's own date
        # fields, which always come back as "2026-09-09T12:44:13.789Z" or
        # similar, never a bare date). datetime.fromisoformat() accepts
        # both, and the caller's own SQL "Date" column truncates the time
        # component on write anyway -- but the full-precision datetime is
        # still what gets returned here, in memory, before that write, which
        # sync's polling watermark computation depends on (see
        # poll_table_sync in sync_tasks.py: it needs the actual timestamp,
        # not the day-only value the column ends up storing).
        try:
            return datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise ValidationError(f"'{value}' is not a valid ISO date") from exc


@register_field_type("single_select")
class SingleSelectFieldType(BaseFieldType):
    key = "single_select"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return String(255)

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        if value is None:
            return None
        choices = {c["value"] for c in options.get("choices", [])}
        if choices and value not in choices:
            raise ValidationError(f"'{value}' is not one of the configured choices")
        return str(value)


@register_field_type("attachment")
class AttachmentFieldType(BaseFieldType):
    """Stores a list of attachment descriptors ({id, filename, size,
    content_type, storage_key}) as JSONB — the descriptors themselves are
    only ever written by app.modules.attachments.service (via the normal
    record-update path), never accepted raw from a client PATCH, so no
    per-key shape validation happens here beyond "it's a list"."""

    key = "attachment"

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        return JSONB()

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValidationError("Attachment field expects a list of attachment descriptors")
        return value

    def from_storage(self, raw: Any, options: dict[str, Any]) -> Any:
        # storage_key is an internal filesystem path -- never echo it back to
        # the client; download-by-id is how a client fetches the bytes.
        return [{k: v for k, v in item.items() if k != "storage_key"} for item in (raw or [])]
