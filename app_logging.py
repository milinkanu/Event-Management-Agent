"""Common logging setup for the poster automation app."""

import logging
import sys


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level=logging.INFO):
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return root_logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    return root_logger


def get_logger(name):
    configure_logging()
    return logging.getLogger(name)
