"""Logging for NetForge.

NetForge uses the standard library's :mod:`logging`.  Every module obtains
its logger through :func:`get_logger`, and the logger's name is the module's
dotted path -- so a record says exactly which part of the framework said it.

The framework never configures the root logger on import.  An application
that embeds NetForge decides how its logs are handled; the CLI adapter
configures logging for itself when it runs.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = ["configure_logging", "get_logger", "NETFORGE_LOGGER_NAME"]

NETFORGE_LOGGER_NAME = "netforge"

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the logger for ``name``, defaulting to the framework logger."""
    if not name:
        return logging.getLogger(NETFORGE_LOGGER_NAME)
    if name.startswith(NETFORGE_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{NETFORGE_LOGGER_NAME}.{name}")


def configure_logging(
    level: str | int = "INFO",
    *,
    stream: Any = None,
    fmt: str = _FORMAT,
) -> logging.Logger:
    """Configure the ``netforge`` logger and return it.

    A handler is attached only once, so calling this twice does not
    duplicate every record.
    """
    logger = logging.getLogger(NETFORGE_LOGGER_NAME)
    logger.setLevel(level)

    if not any(getattr(h, "_netforge_managed", False) for h in logger.handlers):
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(fmt))
        handler._netforge_managed = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

    logger.propagate = False
    return logger
