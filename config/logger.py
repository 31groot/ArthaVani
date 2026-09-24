import logging
import sys

from config.constants import LOG_FORMAT, LOG_DATE_FORMAT
from config.settings import settings

def setup_logger() -> logging.Logger:

    logger = logging.getLogger("arthavani")

    # avoid duplication 
    if logger.hasHandlers():
        return logger

    level_name = str(settings.LOG_LEVEL).upper()
    logger.setLevel(logging._nameToLevel.get(level_name, logging.INFO))

    console_handler = logging.StreamHandler(sys.stderr)

    formatter = logging.Formatter(
        fmt=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )

    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger

logger = setup_logger()