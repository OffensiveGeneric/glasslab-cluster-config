"""Structured JSON logging for the agent API.

One log line per record in a form Cloud Logging can parse, with caller-supplied
extra fields collected into a 'context' object. configure_logging is called once
at startup so every logger in the process shares the same formatter.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


# LogRecord's built-in keys are excluded from 'context' so only caller-supplied
# extras (like experiment_id) are captured as structured fields.
STANDARD_RECORD_KEYS = {
    'args',
    'asctime',
    'created',
    'exc_info',
    'exc_text',
    'filename',
    'funcName',
    'levelname',
    'levelno',
    'lineno',
    'module',
    'msecs',
    'message',
    'msg',
    'name',
    'pathname',
    'process',
    'processName',
    'relativeCreated',
    'stack_info',
    'thread',
    'threadName',
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_RECORD_KEYS and not key.startswith('_')
        }
        if extras:
            payload['context'] = extras
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
