"""Minimal JSON log formatter.

Written by hand rather than pulled in as a dependency because the whole thing
is twenty lines, and `ensure_ascii=False` matters here: log lines carry Persian
text and escaping it to \\uXXXX makes production logs unreadable.
"""

import json
import logging

_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Anything passed as logger.info("...", extra={"room_id": x}) lands here,
        # which is how the roadmap's event counters stay machine-readable.
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)
