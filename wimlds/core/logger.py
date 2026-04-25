"""Structured logging with Rich — mirrors main codebase logger."""
import logging
from pathlib import Path
from rich.logging import RichHandler
from rich.console import Console

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
console = Console()

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"wimlds.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    rh = RichHandler(console=console, show_time=True, show_path=False,
                     markup=True, rich_tracebacks=True)
    rh.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / "post_event.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
    logger.addHandler(rh)
    logger.addHandler(fh)
    return logger




