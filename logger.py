import logging
import os

from config import *

def get_logger():
    formatter = logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s",
                                  "%d-%m-%Y %H:%M:%S")

    os.makedirs(LOG_DIR, exist_ok=True)
    fileHandler = logging.FileHandler(os.path.join(LOG_DIR, "work.log"), encoding="utf-8")
    fileHandler.setFormatter(formatter)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    logger.addHandler(fileHandler)
    logger.addHandler(consoleHandler)

    return logger