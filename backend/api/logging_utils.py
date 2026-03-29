import logging
import os
from typing import Any, Dict


def get_logger(name: str) -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )

    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


def preview_text(value: Any, limit: int = 80) -> str:
    if value is None:
        return ""

    text = str(value).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def build_log_context(**context: Any) -> str:
    parts = []
    for key, value in context.items():
        if value is None:
            continue
        parts.append(f"{key}={value!r}")
    return " ".join(parts)


def log_event(logger: logging.Logger, level: int, event: str, **context: Any) -> None:
    context_text = build_log_context(**context)
    if context_text:
        logger.log(level, "%s | %s", event, context_text)
        return
    logger.log(level, event)


def build_error_payload(stage: str, exc: Exception, **context: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": str(exc),
        "error_type": type(exc).__name__,
        "error_stage": stage,
    }
    filtered_context = {key: value for key, value in context.items() if value is not None}
    if filtered_context:
        payload["error_context"] = filtered_context
    return payload
