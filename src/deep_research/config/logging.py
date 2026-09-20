"""Structured logging configuration with automated secret masking."""

import logging
import re
import sys
from typing import Any, cast

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

# Regex patterns matching known API key signatures
SECRET_PATTERNS = [
    # Google AI / Gemini API keys
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{30,45}"), "AIzaSy...[REDACTED]"),
    # Tavily API keys
    (re.compile(r"tvly-[A-Za-z0-9_-]{25,45}"), "tvly-...[REDACTED]"),
    # Anthropic API keys (must be before general sk-)
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{30,70}"), "sk-ant-...[REDACTED]"),
    # OpenAI project keys (must be before general sk-)
    (re.compile(r"sk-proj-[A-Za-z0-9_-]{30,70}"), "sk-proj-...[REDACTED]"),
    # OpenAI standard API keys
    (re.compile(r"sk-[A-Za-z0-9_-]{30,60}"), "sk-...[REDACTED]"),
    # Bearer tokens in headers
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"), "Bearer [REDACTED]"),
]

SENSITIVE_KEY_NAMES = {
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "auth",
    "authorization",
    "gemini_api_key",
    "tavily_api_key",
    "openai_api_key",
    "anthropic_api_key",
}


def mask_secrets(value: Any) -> Any:
    """Recursively mask secrets in strings, lists, or dictionary values."""
    if isinstance(value, str):
        masked = value
        for pattern, replacement in SECRET_PATTERNS:
            masked = pattern.sub(replacement, masked)
        return masked
    elif isinstance(value, dict):
        masked_dict: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in SENSITIVE_KEY_NAMES and isinstance(v, str) and v:
                # Mask key value completely if key name is sensitive
                masked_dict[k] = f"{v[:6]}...[REDACTED]" if len(v) > 8 else "[REDACTED]"
            else:
                masked_dict[k] = mask_secrets(v)
        return masked_dict
    elif isinstance(value, (list, tuple)):
        return [mask_secrets(item) for item in value]
    return value


def secret_masking_processor(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Structlog processor that sanitizes sensitive data before output."""
    for key, value in list(event_dict.items()):
        if str(key).lower() in SENSITIVE_KEY_NAMES and isinstance(value, str) and value:
            event_dict[key] = f"{value[:6]}...[REDACTED]" if len(value) > 8 else "[REDACTED]"
        else:
            event_dict[key] = mask_secrets(value)
    return event_dict


def configure_logging(level: str = "INFO", structured: bool = False) -> None:
    """Configure system-wide structured logging and standard library bridges."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        secret_masking_processor,
    ]

    processors: list[Processor]
    if structured:
        # Machine-readable JSON output for production environments
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable colorized terminal output for CLI & development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    # Bridge standard library logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=log_level,
        force=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Obtain a structured logger bound with optional component name."""
    logger = cast(structlog.BoundLogger, structlog.get_logger())
    if name:
        return logger.bind(component=name)
    return logger
