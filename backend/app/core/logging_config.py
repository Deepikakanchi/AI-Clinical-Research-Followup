"""Structured JSON logging that never writes sensitive content (US-31).

Use log_event(logger, "event_name", key=value, ...). Keys that could carry
personal data or study text (names, emails, notes, drafts, tokens) are dropped
automatically and listed under "redacted_fields" so the omission is visible.
"""
import json
import logging
import sys
from datetime import datetime, timezone

BLOCKED_KEYS = {
    "email", "full_name", "name",
    "observation_text", "follow_up_actions", "note", "notes",
    "generated_draft", "draft", "visit_summary", "final_text", "reviewer_comment", "reason",
    "prompt", "messages", "api_key", "token", "authorization", "password", "secret",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            data.update(fields)
        if record.exc_info and record.exc_info[0] is not None:
            # Type only: exception messages can contain SQL parameters or text.
            data["exception_type"] = record.exc_info[0].__name__
        return json.dumps(data, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Uvicorn's access log prints full URLs; ours below is enough.
    logging.getLogger("uvicorn.access").disabled = True


def safe_fields(fields: dict) -> dict:
    safe = {k: v for k, v in fields.items() if k.lower() not in BLOCKED_KEYS}
    dropped = sorted(k for k in fields if k.lower() in BLOCKED_KEYS)
    if dropped:
        safe["redacted_fields"] = dropped
    return safe


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": {"event": event, **safe_fields(fields)}})