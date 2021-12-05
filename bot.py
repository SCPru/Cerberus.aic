from core.wikidot import Wikidot
from core.modules import ModuleLoader
from core.logger import LOG_LEVELS, log
import config

from prettytable import PrettyTable
from periodic import Periodic
from typing import List
import argparse
import asyncio
import os


def get_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="print bot version - will not run the bot",
    )
    parser.add_argument(
        "-m",
        "--modules",
        action="store_true",
        help="print module list - will not run the bot",
    )
    parser.add_argument(
        "--logging_level",
        choices=list(LOG_LEVELS),
        help="the level to use for logging - defaults to INFO",
        default="INFO",
    )

    return parser


class Bot:
    config = config.load_config("bot")

    def __init__(self):
        self._wikidot = Wikidot(self.config["wikidot"]["wikis"])
        self._wikidot.auth(os.getenv("CERBERUS_LOGIN"), os.getenv("CERBERUS_PASSWORD"))

    def run(self):
        log.info("Initializing SkippyBot")

        log.info("Load all modules...")
        module_loader = ModuleLoader()
        module_loader.load_modules()

        log.info("Start all modules...")
        module_loader.start_modules()

        loop = asyncio.get_event_loop()
        try:
            loop.create_task(self.main(list(module_loader.tasks)))
            loop.run_forever()
        except:
            pass
        finally:
            loop.stop()

        log.info("Stop all modules...")
        module_loader.stop_modules()

    @staticmethod
    async def main(tasks: List[Periodic]):
        for task in tasks:
            await task.start()

    @classmethod
    def get_version(cls):
        return cls.config["version"]


def modules_data():
    table = PrettyTable()
    table.field_names = ["Alias", "Description", "Author", "Version"]

    for module in ModuleLoader.modules_data():
        table.add_row(
        [
            module["__alias__"],
            module["__description__"],
            module["__author__"],
            module["__version__"],
        ]
    )

    return table


def start():
    args = get_argparser().parse_args()

    log.setLevel(LOG_LEVELS[args.logging_level])

    if args.version:
        print(f"Bot version: v{Bot.get_version()}")
    elif args.modules:
        print(modules_data())
    else:
        bot = Bot()
        bot.run()
