"""Database orm
"""
import config

from peewee import SqliteDatabase, Model
import os


def make_file(file: str):
    """Create empty file by file name

    Args:
      file (str): File name
    """
    if not os.path.exists(file):
        with open(file, "w") as f:
            f.write("")


db_path = os.path.join(config.BOT_FOLDER, "database.db")
make_file(db_path)

database = SqliteDatabase(db_path)


class BaseModel(Model):
    class Meta:
        database = database
