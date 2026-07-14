"""Root logging configuration for standalone execution."""

import logging
import os

_HANDLER_MARKER = "_discord_youtube_streamer_handler"


def configure_logging() -> None:
    """Configure logging once, honoring the optional LOG_LEVEL setting."""
    root_logger = logging.getLogger()
    if any(getattr(handler, _HANDLER_MARKER, False) for handler in root_logger.handlers):
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
        )
    )
    setattr(handler, _HANDLER_MARKER, True)
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


__all__ = ["configure_logging"]
