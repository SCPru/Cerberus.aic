from __future__ import annotations

from typing import Iterable, Optional, Dict, Any, List
from functools import cached_property
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from aiohttp import ClientSession
from copy import deepcopy
from yarl import URL

from .utils import lazy_async, never, page_category, normalize_tag

import inspect
import logging

class APIData:
    @classmethod
    def from_dict(cls, parameters):
        allowed_parameters = inspect.signature(cls).parameters
        filtered_parameters = {k: v for k, v in parameters.items() if k in allowed_parameters}
        return cls(**filtered_parameters)

class Method(Enum):
    GET = auto()
    POST = auto()
    PUT = auto()
    DELETE = auto()

@dataclass
class Route:
    endpoint: str
    method: Method = Method.GET

class Endpoint(Enum):
    Modules = Route("modules", Method.POST)
    Articles = Route("articles")
    Article = Route("articles/{}")
    ArticleLog = Route("articles/{}/log")

    def get_endpoint_route(self, page_id: str, method: Optional[Method]=None):
        route = deepcopy(self.value)
        if method:
            route.method = method
        route.endpoint = route.endpoint.format(page_id)
        
        return route

class Module(Enum):
    Rate = "rate"
    ListPages = "listpages"
    ListUsers = "listusers"
    ForumNewPost = "forumnewpost"
    ForumThread = "forumthread"

@dataclass
class User(APIData):
    type: str
    id: int
    avatar: Optional[str]
    showAvatar: bool
    name: str
    username: str
    staff: bool
    admin: bool

SYSTEM_USER = User("system", -1, None, False, "System", "System", True, True)


class LogEntryType(Enum):
    New = "new"
    Tags = "tags"
    Name = "name"
    Source = "source"
    Revert = "revert"


@dataclass
class LogEntry(APIData):
    revNumber: int
    user: User
    comment: str
    createdAt: datetime
    type: str
    meta: Dict[str, Any]

    @classmethod
    def from_dict(cls, parameters) -> LogEntry:
        parameters["createdAt"] = datetime.fromisoformat(parameters["createdAt"])
        parameters["user"] = User.from_dict(parameters["user"])
        return super().from_dict(parameters)


@dataclass
class Vote(APIData):
    user: User
    value: float

class VotesMode(Enum):
    UpDown = "updown"
    Stars = "stars"
    Disabled = "disabled"

@dataclass
class PageMeta:
    name: Optional[str] = None
    title: Optional[str] = None
    author: Optional[User] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    rating: Optional[float] = None
    popularity: Optional[int] = None
    votes_count: Optional[int] = None
    votes_mode: Optional[VotesMode] = None
    tags: Optional[List[str]] = None

class Page:
    def __init__(self, wiki: Wiki, page_id: str):
        self.wiki = wiki
        self.page_id = page_id

        self._raw_data = None
        self._article_log = None
        self._votes_info = None
        self._meta: PageMeta = PageMeta()

    def __repr__(self):
        view = f"{self.name}"
        view += f" ({self.title})" if self.title is not None else ""
        view += f" {self.rating if self.rating is not None else "?"} ({self.votes_count if self.votes_count is not None else "?"}) / {self.popularity if self.popularity is not None else "?"}%"
        view += f" {self.author.username}" if self.author is not None else ""
        view += f" {self.tags}" if self._meta.tags is not None else ""

        return view

    async def fetch(self) -> Page:
        await self.get_page_data()
        await self.get_change_log()
        await self.get_votes_info()

        return self

    async def update_data(self, data: Any) -> Any:
        if "pageId" not in data:
            data["pageId"] = self.page_id
        return await self.wiki.api(Endpoint.Article.get_endpoint_route(self.page_id, Method.PUT), json=data)

    @property
    def title(self) -> str | None:
        return self._meta.title

    @property
    def source(self) -> str | None:
        if not self._raw_data or "source" not in self._raw_data:
            return None
        return self._raw_data["source"]

    @property
    def name(self) -> str:
        return self.page_id
    
    @property
    def category(self) -> str:
        return page_category(self.page_id)

    @property
    def tags(self) -> List[str]:
        return self._meta.tags or []
    
    @property
    def history(self) -> List[LogEntry]:
        if not self._article_log:
            return []
        return [LogEntry.from_dict(entry) for entry in deepcopy(self._article_log["entries"])]

    @property
    def created_at(self) -> datetime:
        return self._meta.created_at or never()
    
    @property
    def updated_at(self) -> datetime:
        return self._meta.updated_at or never()

    @cached_property
    def author(self) -> User:
        return self._meta.author or SYSTEM_USER

    @property
    def votes(self) -> List[Vote]:
        if not self._votes_info:
            return []
        return [Vote.from_dict(vote) for vote in self._votes_info["votes"]]
    
    @property
    def votes_count(self) -> int:
        return self._meta.votes_count or -1
    
    @property
    def rating(self) -> float:
        return self._meta.rating or float('-inf')

    @property
    def popularity(self) -> int:
        return self._meta.popularity or -1
    
    async def is_exists(self):
        return await self.wiki.is_page_exists(self.page_id)
    
    async def filter_history(self, types: Optional[List[LogEntryType] | List[str]]=None, lazy: bool=True) -> List[LogEntry]:
        await lazy_async(lazy, self.history is None, self.get_change_log)

        if not types:
            return self.history

        types = [type.value if isinstance(type, LogEntryType) else type for type in types]

        return [entry for entry in self.history if entry.type in types]
    
    async def get_page_data(self) -> Any:
        self._raw_data = await self.wiki.api(Endpoint.Article.get_endpoint_route(self.page_id))
        self._meta.title = self._raw_data['title']
        self._meta.tags = self._raw_data["tags"]
        return self._raw_data
    
    async def get_change_log(self) -> Any:
        self._article_log = await self.wiki.api(Endpoint.ArticleLog.get_endpoint_route(self.page_id), params={"all": "true"})
        history = self.history

        self._meta.created_at = history[-1].createdAt
        self._meta.updated_at = history[0].createdAt
        self._meta.author = history[-1].user
        return self._article_log
    
    async def get_votes_info(self) -> Any:
        self._votes_info = await self.wiki.module(Module.Rate, "get_votes", pageId=self.page_id)
        self._meta.rating = self._votes_info["rating"]
        self._meta.popularity = self._votes_info["popularity"]
        self._meta.votes_count = len(self._votes_info["votes"])
        return self._votes_info
    
    async def get_last_category_move(self, lazy: bool=True) -> LogEntry:
        await lazy_async(lazy, self.history is None, self.get_change_log)

        for entry in await self.filter_history([LogEntryType.Name]):
            new_category = page_category(entry.meta["name"])
            prev_category = page_category(entry.meta["prev_name"])
            if new_category == self.category and new_category != prev_category:
                return entry
            
        return self.history[-1]
    
    async def get_last_source_edit(self, lazy: bool=True) -> LogEntry:
        await lazy_async(lazy, self.history is None, self.get_change_log)

        edits = await self.filter_history([LogEntryType.Source, LogEntryType.New])
        return edits[0]
    
    async def get_tag_date(self, tag: str, lazy: bool=True) -> datetime | None:
        await lazy_async(lazy, self.tags is None, self.get_page_data)

        normalized_tag = normalize_tag(tag)

        if normalized_tag not in self.tags:
            return None
        
        for entry in await self.filter_history([LogEntryType.Tags]):
            if normalized_tag in [tag_entry["name"] for tag_entry in entry.meta["added_tags"]]:
                return entry.createdAt
            
        return None
    
    async def set_tags(self, tags: Iterable[str]):
        return await self.update_data({"tags": tags})
    
    async def add_tags(self, tags: Iterable[str], lazy: bool=True):
        await lazy_async(lazy, self.tags is None, self.get_page_data)

        new_tags = self.tags
        new_tags.extend(map(normalize_tag, tags))
        return await self.set_tags(list(set(new_tags)))
    
    async def remove_tags(self, tags: Iterable[str], lazy: bool=True) -> List[str]:
        await lazy_async(lazy, self.tags is None, self.get_page_data)

        new_tags = self.tags
        removed_tags = []

        for tag in tags:
            normalized_tag = normalize_tag(tag)
            if normalized_tag in new_tags:
                new_tags.remove(normalized_tag)
                removed_tags.append(normalized_tag)
        await self.set_tags(new_tags)
        return removed_tags

    async def update_tags(self, add_tags: Optional[List[str]]=None, remove_tags: Optional[List[str]]=None, lazy: bool=True):
        await lazy_async(lazy, self.tags is None, self.get_page_data)

        new_tags = self.tags
        removed_tags = []

        if remove_tags is not None:
            for tag in remove_tags:
                normalized_tag = normalize_tag(tag)
                if normalized_tag in new_tags:
                    new_tags.remove(normalized_tag)
                    removed_tags.append(normalized_tag)

        if add_tags is not None:
            new_tags.extend(map(normalize_tag, add_tags))

        await self.set_tags(new_tags)
        return removed_tags

    async def delete_page(self) -> Any:
        return await self.wiki.api(Endpoint.Article.get_endpoint_route(self.page_id, Method.DELETE))

    async def rename(self, new_id: str) -> str:
        result = await self.update_data({"pageId": new_id, "forcePageId": True})
        self.page_id = result['pageId']
        return self.page_id

    async def get_thread(self) -> ForumThread:
        return ForumThread(
            self.wiki,
            (await self.wiki.module(Module.ForumThread, "for_article", pageId=self.page_id))["threadId"]
        )


class ForumThread:
    def __init__(self, wiki: Wiki, thread_id: str, page: Optional[Page] = None):
        self.wiki = wiki
        self.thread_id = thread_id

    async def new_post(self, source: str, title: Optional[str] = None):
        params = {
            "threadid": self.thread_id,
            "name": title,
            "source": source,
        }
        return await self.wiki.module(Module.ForumNewPost, "submit", params=params)


class Wiki:
    def __init__(self, wiki_base: str, token: Optional[str]=None):
        self.wiki_base = URL(wiki_base)
        self.token = token
        self._logger = logging.getLogger()
        self._session: ClientSession
        self._api_url = URL("/api/")
        self.is_api_initialized = False

    async def _init_api(self):
        self._session = ClientSession(self.wiki_base)
        self._session.headers.add("Authorization", f"Bearer {self.token}")
        self.is_api_initialized = True

    async def _close_api(self):
        if self._session:
            await self._session.close()

    async def api(self, endpoint: Endpoint | Route, raw: bool=False, *args, **kwargs) -> Any:
        if not self.is_api_initialized:
            await self._init_api()

        if isinstance(endpoint, Endpoint) :
            route = endpoint.value
        else:
            route = endpoint

        self._logger.debug(f"API call to endpoint: {self.wiki_base.join(self._api_url) / route.endpoint} with args: {args} and kwargs: {kwargs}")
        
        resp = await self._session.request(route.method.name, self._api_url / route.endpoint, *args, **kwargs)
        if raw:
            return resp
        resp.raise_for_status()
        return await resp.json()
        
    async def get_page(self, page_id: str, lazy: bool=True) -> Page:
        if lazy:
            return Page(self, page_id)
        return await Page(self, page_id).fetch()
    
    async def is_page_exists(self, page_id: str):
        log =  await self.api(Endpoint.ArticleLog.get_endpoint_route(page_id))
        return log["count"] > 0
    
    async def get_all_pages(self):
        all_pages_json = await self.api(Endpoint.Articles)
        all_pages = []
        for page_data in all_pages_json:
            page = Page(self, page_data["pageId"])
            page._meta = PageMeta(
                name=page_data["pageId"],
                title=page_data["title"],
                author=User.from_dict(page_data["createdBy"]),
                created_at=datetime.fromisoformat(page_data["createdAt"]),
                updated_at=datetime.fromisoformat(page_data["updatedAt"]),
                rating=page_data["rating"]["value"],
                popularity=page_data["rating"]["popularity"],
                votes_count=page_data["rating"]["votes"],
                votes_mode=VotesMode(page_data["rating"]["mode"]),
                tags=page_data["tags"]
            )
            all_pages.append(page)
        return all_pages
        
    async def _module(self, name: str, method: str, **kwargs) -> Any:
        data = {"module": name, "method": method}
        data.update(kwargs)
        return await self.api(Endpoint.Modules, json=data)
    
    async def module(self, module: Module, method: str, **kwargs) -> Any:
        return await self._module(module.value, method, **kwargs)
    
    async def _raw_list_pages(self, **params) -> Any:
        return await self.module(Module.ListPages, "get", params=params)
    
    async def list_pages(self, **params) -> List[Page]:
        return [await self.get_page(page_id) for page_id in (await self._raw_list_pages(**params))["pages"]]
    
    @staticmethod
    async def filter_pages(pages: List[Page], categories: str="_default", tags: str="", lazy: bool=True) -> list[Page]:
        tags_require = set()
        tags_include = set()
        tags_exclude = set()
        filtered_pages = []

        tags_list = tags.split()
        categories_list= categories.split()

        for tag in tags_list:
            if tag.startswith("+"):
                tags_require.add(tag[1:])
            elif tag.startswith("-"):
                tags_exclude.add(tag[1:])
            else:
                tags_include.add(tag)

        for page in pages:
            if categories_list and page.category in categories_list:
                await lazy_async(lazy, page.tags is None, page.get_page_data)
                page_tags = set(page.tags)
                if all((tags_require.issubset(page_tags), 
                       (not tags_exclude.intersection(page_tags)) if tags_exclude else True, 
                        tags_include.intersection(page_tags) if tags_include else True)):
                    filtered_pages.append(page)

        return filtered_pages
    
    @staticmethod
    async def only_exists(pages: List[Page]) -> list[Page]:
        return [page for page in pages if await page.is_exists()]