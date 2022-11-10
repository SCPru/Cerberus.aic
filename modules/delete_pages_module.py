from core.wiki import Thread, Wiki, Page
from core.modules import AbstractModule
from core.logger import log
from core.db import BaseModel

from typing import Iterator, Dict, Any, List
from asyncio import sleep
import random
import peewee
import arrow


class PageForDelete(BaseModel):
    wiki = peewee.CharField()
    name = peewee.CharField()
    timestamp = peewee.FloatField()


class DeletePagesModule(AbstractModule):
    __alias__: str = "DeletePages"
    __description__: str = "Делаем работу заместо Арбеликта"
    __author__: str = "MrNereof"
    __version__: str = "1.0.0"

    interval = 300

    def __init__(self, *args, **kwargs):
        super(DeletePagesModule, self).__init__(*args, **kwargs)
        if not PageForDelete.table_exists():
            PageForDelete.create_table()

    async def onRun(self):
        await self.find_new_critical_pages()
        await self.delete_pages()

    async def find_new_critical_pages(self):
        print(1)
        for page in self.get_critical_rate_pages():
            print(page)
            await self.prepare_page(page)
        # for page in self.get_old_pages():
        #     await self.prepare_page(page)

    async def prepare_page(self, page: Page):
        if self.validate_page(page):
            log.debug(f"Find page: {page.title}")

            tags = page.tags
            tags.append(self.config["deletes_tag"])
            page.set_tags(tags)
            PageForDelete.create(wiki=page.wiki, name=page.name, timestamp=arrow.utcnow().timestamp).save()

            await self.post_comment(page)

    async def delete_pages(self):
        pages = []
        for page in PageForDelete.select():
            if arrow.utcnow().timestamp - page.timestamp >= self.config["time"]:
                try:
                    p = self.wiki.get(page.name)
                    pages.append({"title": p.title, "rating": p.rating, "user": p.author.username})
                    p.delete_page()

                    log.debug(f"Page was deleted: {page.name}")
                    page.delete_instance()
                except AttributeError:
                    page.delete_instance()
                except NotImplementedError:
                    pass
                page.save()

        if pages:
            await self.log_deleted(pages)

    def get_critical_rate_pages(self) -> List[Page]:
        return [page for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"{' '.join(self.config['tags'])} -{self.config['deletes_tag']}",
            rating=f"<={self.config['critical']['rate']}"
        ) if len(page.votes) >= self.config["critical"]["num"]]

    def get_old_pages(self) -> Iterator[Page]:
        for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"{' '.join(self.config['tags'])} -{self.config['deletes_tag']}",
            rating=f"<{self.config['week']['rate']}"
        ):
            if (arrow.now() - arrow.get(page.created, "YYYY-MM-DD HH:mm:ss")).days >= self.config["week"]["days"]:
                yield page

    async def post_comment(self, page: Page):
        conf = self.config["post"]
        source = conf["source"] if random.random() > 0.25 else conf["easter_eggs"][random.choice(list(conf["easter_eggs"]))]
        try:
            page.thread.new_post(source, conf["title"])
        except RuntimeError as exc:
            if getattr(exc, "message", None) == "try_again":
                await self.post_comment(page)

    async def log_deleted(self, list_page: List[Dict[str, Any]]):
        conf = self.config["log"]

        try:
            Thread(self.wiki, conf["id"]).new_post(conf["source"].format("\n".join(
                [conf["list_template"].format(**page) for page in
                    list_page])), conf["title"])
        except RuntimeError as exc:
            if getattr(exc, "message", None) == "try_again":
                await self.log_deleted(list_page)

    def validate_page(self, page: Page) -> bool:
        return self.config["deletes_tag"] not in self.wiki.get(page.name).tags


def load(*args, **kwargs) -> DeletePagesModule:
    return DeletePagesModule(*args, **kwargs)
