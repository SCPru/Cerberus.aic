import logging
import os

from config import config, DEBUG

def get_logger():
    formatter = logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s",
                                  "%d-%m-%Y %H:%M:%S")

    os.makedirs(config["logs_dir"], exist_ok=True)
    fileHandler = logging.FileHandler(os.path.join(config["logs_dir"], "work.log"), encoding="utf-8")
    fileHandler.setFormatter(formatter)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    logger.addHandler(fileHandler)
    logger.addHandler(consoleHandler)

    return logger