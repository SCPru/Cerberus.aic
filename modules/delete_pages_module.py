from core.wiki import Thread, Wiki, Page
from core.modules import AbstractModule
from core.logger import log

from typing import Iterator, Dict, Any, List
from datetime import datetime
import random
import arrow


class DeletePagesModule(AbstractModule):
    __alias__: str = "DeletePages"
    __description__: str = "Делаем работу заместо Арбеликта"
    __author__: str = "MrNereof"
    __version__: str = "1.0.0"

    interval = 900

    async def onRun(self):
        await self.find_new_critical_pages()
        await self.delete_pages()

    async def find_new_critical_pages(self):
        for page in self.get_critical_rate_pages():
            await self.prepare_page(page)
        # for page in self.get_old_pages():
        #     await self.prepare_page(page)

    async def prepare_page(self, page: Page):
        if self.validate_page(page):
            log.debug(f"Find page: {page.title}")

            tags = page.tags
            tags.append(self.config["deletes_tag"])
            page.set_tags(tags)

            await self.post_comment(page)

    @staticmethod
    def _get_date_of_for_delete(page: Page) -> datetime:
        return [entry for entry in page.history if "_for_delete" in entry.meta.get("added_tags", [])][0].createdAt

    async def delete_pages(self):
        pages = []
        for page in self.wiki.list_pages(tags=self.config["deletes_tag"]):
            if arrow.utcnow().timestamp - self._get_date_of_for_delete(page).timestamp() >= self.config["time"]:
                pages.append({"title": page.title, "rating": page.rating, "user": page.author.username})
                page.delete_page()

                log.debug(f"Page was deleted: {page.name}")

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
