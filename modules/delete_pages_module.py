from core.wikidot import Thread, Wiki, Page
from core.modules import AbstractModule
from core.logger import log
from core.db import BaseModel

from typing import Iterator, Tuple, List
from asyncio import sleep
import random
import peewee
import arrow


class PageForDelete(BaseModel):
    """ """
    wiki = peewee.CharField()
    name = peewee.CharField()
    timestamp = peewee.FloatField()


class DeletePagesModule(AbstractModule):
    __alias__: str = "DeletePages"
    __description__: str = "Делаем работу заместо Арбеликта"
    __author__: str = "MrNereof"
    __version__: str = "1.0.0"

    interval = 60

    def __init__(self):
        super(DeletePagesModule, self).__init__()
        if not PageForDelete.table_exists():
            PageForDelete.create_table()

    async def onRun(self):
        await self.find_new_critical_pages()
        await self.delete_pages()

    async def find_new_critical_pages(self):
        for wiki in self._wikidot.wikis:
            for page in self.get_critical_rate_pages(wiki):
                await self.prepare_page(page)
            for page in self.get_old_pages(wiki):
                await self.prepare_page(page)

    async def prepare_page(self, page: Page):
        if self.validate_page(page):
            log.debug(f"Find page: {page.title}")

            tags = page.tags
            tags.add(self.config["deletes_tag"])
            page.set_tags(tags)

            PageForDelete.create(wiki=page._wiki, name=page.name, timestamp=arrow.utcnow().timestamp)

            await self.post_comment(page)

    async def delete_pages(self):
        pages = []
        for page in PageForDelete.select():
            if arrow.utcnow().timestamp - page.timestamp >= self.config["time"]:
                try:
                    wiki = self._wikidot.get_wiki(page.wiki)
                    p = wiki(page.name)
                    pages.append((p.title, p.author, p.rating))
                    p.delete_page()

                    log.debug(f"Page was deleted: {page.name}")
                    page.delete_instance()
                except NotImplementedError:
                    pass
                page.save()

        if pages:
            await self.log_deleted(pages)

    def get_critical_rate_pages(self, wiki: Wiki) -> Iterator[Page]:
        return wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"{' '.join(self.config['tags'])} -{self.config['deletes_tag']}",
            rating=f"<{self.config['critical']['rate'] + 1}"
        )

    def get_old_pages(self, wiki: Wiki) -> Iterator[Page]:
        for page in wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"{' '.join(self.config['tags'])} -{self.config['deletes_tag']}",
            rating=f"<{self.config['week']['rate']}"
        ):
            if (arrow.now() - arrow.get(page.created, "YYYY-MM-DD HH:mm:ss")).days >= self.config["week"]["days"]:
                yield page

    async def post_comment(self, page: Page):
        await sleep(6)

        conf = self.config["post"]
        source = conf["source"] if random.random() > 0.25 else conf["easter_eggs"][random.choice(list(conf["easter_eggs"]))]
        try:
            page._thread.new_post(source, conf["title"])
        except RuntimeError as exc:
            if getattr(exc, "message", None) == "try_again":
                await self.post_comment(page)

    async def log_deleted(self, list_page: List[Tuple[str, int, str]]):
        for wiki in self._wikidot.wikis:
            conf = self.config["log"]

            try:
                Thread(wiki, conf["id"]).new_post(conf["source"].format("\n".join(
                    [conf["list_template"].format(*page) for page in
                     list_page])), conf["title"])
            except RuntimeError as exc:
                if getattr(exc, "message", None) == "try_again":
                    await self.log_deleted(list_page)

    def validate_page(self, page: Page) -> bool:
        return self.config["deletes_tag"] not in self._wikidot.get_wiki(page._wiki.wiki)(page.name).tags


def load() -> DeletePagesModule:
    return DeletePagesModule()
