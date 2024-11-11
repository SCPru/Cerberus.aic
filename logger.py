import logging
import os

def get_logger(logs_dir: str="logs/", debug: bool=False):
    formatter = logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s",
                                  "%d-%m-%Y %H:%M:%S")

    os.makedirs(logs_dir, exist_ok=True)
    fileHandler = logging.FileHandler(os.path.join(logs_dir, "work.log"), encoding="utf-8")
    fileHandler.setFormatter(formatter)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(fileHandler)
    logger.addHandler(consoleHandler)

    return logger