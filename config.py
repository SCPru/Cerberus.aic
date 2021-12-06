"""Various utile to easier work with config files
"""
from typing import MutableMapping, Any

import toml
import os


def mkdir(path: str):
    """Make dir by path

    Args:
      path (str): Path to dir
    """
    if not os.path.exists(path):
        os.mkdir(path)


BOT_FOLDER = os.path.dirname(os.path.realpath(__file__))

CONFIG_FOLDER = os.path.join(BOT_FOLDER, "config")
MODULES_FOLDER = os.path.join(BOT_FOLDER, "modules")

LOGS_FOLDER = os.path.join(BOT_FOLDER, "logs")
mkdir(LOGS_FOLDER)


def config_path(file: str) -> str:
    """Get path to config file by file name

    Args:
        file (str): Config file name

    Returns:
        str: Path to config file
    """
    return os.path.join(CONFIG_FOLDER, f"{file}.toml")


def load_config(file: str) -> MutableMapping[str, Any]:
    """Load config file by file name

    Args:
        file (str): Config file name

    Returns:
        MutableMapping[str, Any]: Config dict
    """
    if os.path.exists(config_path(file)):
        with open(config_path(file), "r", encoding="utf-8") as f:
            return toml.load(f)
