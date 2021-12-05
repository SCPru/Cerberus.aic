import toml
import os


def mkdir(path: str):
    if not os.path.exists(path):
        os.mkdir(path)


BOT_FOLDER = os.path.dirname(os.path.realpath(__file__))

CONFIG_FOLDER = os.path.join(BOT_FOLDER, "config")
MODULES_FOLDER = os.path.join(BOT_FOLDER, "modules")

LOGS_FOLDER = os.path.join(BOT_FOLDER, "logs")
mkdir(LOGS_FOLDER)



def config_path(file: str):
    return os.path.join(CONFIG_FOLDER, f"{file}.toml")


def load_config(file: str):
    if os.path.exists(config_path(file)):
        with open(config_path(file), "r", encoding="utf-8") as f:
            return toml.load(f)
