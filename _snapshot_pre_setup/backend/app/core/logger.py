import logging
from typing import Optional


_configured = False


def _configure():
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _configured = True


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    _configure()
    lg = logging.getLogger(name)
    if level is not None:
        lg.setLevel(level)
    return lg
