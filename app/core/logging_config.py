"""Logging setup shared by the API process and standalone scripts."""

from __future__ import annotations

import logging
import sys

from app.config import Settings


def setup_logging(settings: Settings) -> None:
    """Configure the root logger to write to stdout only.

    File locations are deployment concerns: container and platform log
    collectors already capture stdout, so no log path is compiled in.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
