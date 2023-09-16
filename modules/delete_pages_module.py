from core.wiki import Thread, Wiki, Page
from core.modules import AbstractModule
from core.logger import log

from typing import Iterator, Dict, Any, List, Optional
from requests.exceptions import HTTPError
from datetime import datetime, timedelta
import random
import arrow


class DeletePagesModule(AbstractModule):
    __alias__: str = "DeletePages"
    __description__: str = "Делаем работу заместо Арбеликта"
    __author__: str = "MrNereof"
    __version__: str = "2.0.0"

    interval = 900

    async def onRun(self):
        await self.find_new_critical_pages()
        await self.delete_pages()

    async def find_new_critical_pages(self):
        await self.handle_critical_rate_pages()

        await self.mark_month()
        await self.handle_month_pages()

        await self.handle_approved_pages()

    async def prepare_page(self, page: Page):
        if self.validate_page(page):
            log.debug(f"Find page: {page.title}")

            tags = page.tags
            tags.append(self.config["deletes_tag"])
            page.set_tags(tags)

            await self.post_comment(page)

    def _get_date_of_for_delete(self, page: Page) -> datetime:
        try:
            return [entry for entry in page.history if self.config["deletes_tag"] in map(lambda x: x["name"], entry.meta.get("added_tags", []))][0].createdAt
        except IndexError:
            return datetime.now()

    async def delete_pages(self):
        pages = []
        for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=self.config['deletes_tag'],
            rating=f"<={self.config['critical']['rate']}"
        ):
            if arrow.utcnow().timestamp - self._get_date_of_for_delete(page).timestamp() >= self.config["time"]:
                pages.append({"title": page.title, "rating": page.rating, "user": page.author.username})
                page.delete_page()
                log.debug(f"Page was deleted: {page.name}")

        if pages:
            await self.log_deleted(pages)

    async def handle_critical_rate_pages(self):
        for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"{' '.join(self.config['tags'])} -{self.config['deletes_tag']}",
            rating=f"<={self.config['critical']['rate']}",
            votes=f">={self.config['critical']['num']}"
        ):
            await self.prepare_page(page)

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

    @staticmethod
    def _get_timedelta(page: Page) -> timedelta:
        return arrow.now() - arrow.get(page.created)

    async def mark_month(self):
        for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=" ".join(self.config['tags'])
        ):
            if self._get_timedelta(page).days // 30:
                tags = page.tags
                tags.append(self.config['month']['tag'])
                page.set_tags(tags)

    async def handle_month_pages(self):
        for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"+{self.config['month']['tag']} +{self.config['month']['declined_tag']}",
            votes=f">={self.config['month']['num']}"
        ):
            await self.delete_page(page)

    async def delete_page(self, page: Page, new_name: Optional[str] = None):
        if not new_name:
            new_name = page.page_id

        try:
            page.rename(f"deleted:{new_name}")
        except HTTPError as exc:
            if exc.response.status_code == 409:
                await self.delete_page(page, f"{new_name}-2")

    async def handle_approved_pages(self):
        conf = self.config["approved"]
        for page in self.wiki.list_pages(
            category=" ".join(self.config["category"]),
            tags=f"{' '.join(self.config['tags'])} -{conf['approved_tag']}",
            votes=f">={conf['num']}",
            popularity=f">={conf['popularity']}"
        ):
            if self._get_timedelta(page).days / 7 >= conf["weeks"]:
                tags = page.tags
                tags.append(conf['approved_tag'])

                if conf['tags']['protegano'] not in tags:
                    tags.append(conf['tags']['for_tags'])
                page.set_tags(tags)


def load(*args, **kwargs) -> DeletePagesModule:
    return DeletePagesModule(*args, **kwargs)
