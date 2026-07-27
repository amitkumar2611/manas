"""Structured logging with secret scrubbing."""
import logging
import os
import re

_SECRET_PAT = re.compile(r"(token|key|secret|password)=\S+", re.I)


class _Scrub(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _SECRET_PAT.sub(r"\1=***", str(record.msg))
        return True


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(f"manas.{name}")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s level=%(levelname)s mod=%(name)s %(message)s"))
        h.addFilter(_Scrub())
        log.addHandler(h)
        log.setLevel(os.getenv("MANAS_LOG_LEVEL", "INFO"))
    return log
