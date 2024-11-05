from typing import Dict

from os import getenv
from json import loads
from yaml import safe_load
from datetime import timedelta

CONFIG_PATH = "config.yml"

API_TOKEN = getenv("CERBERUS_AUTHKEY")
DEBUG = bool(loads(getenv("DEBUG", "false")))

with open(CONFIG_PATH, "r", encoding="utf-8") as file:
    config = safe_load(file)

def extract_period(param) -> timedelta:
    return timedelta(
        minutes=param.get("minutes", 0),
        hours=param.get("hours", 0),
        days=param.get("days", 0),
        weeks=param.get("weeks", 0)
    )