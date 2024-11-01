from __future__ import annotations

from typing import Optional, Dict, Any, List
from functools import cached_property
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from aiohttp import request, client_exceptions
from copy import deepcopy
from yarl import URL

from .utils import lazy_async, page_category, normalize_tag, random_string

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
    Article = Route("articles/{}")
    ArticleLog = Route("articles/{}/log")

    def get_endpoint_route(self, page_id: str, method: Method=None):
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

class Page:
    def __init__(self, wiki: Wiki, page_id: str):
        self.wiki = wiki
        self.page_id = page_id

        self._raw_data = None
        self._article_log = None
        self._votes_info = None

    def __repr__(self):
        view = f"{self.name}"
        view += f" ({self.title})" if self._raw_data is not None else ""
        view += f" {self.rating} ({self.votes_count}) / {self.popularity}%" if self._votes_info is not None else ""
        view += f" {self.author.username}" if self._article_log is not None else ""
        view += f" {self.tags}" if self._raw_data is not None else ""

        return view

    async def fetch(self):
        await self._get_raw_data()
        await self.get_article_log()
        await self.get_votes_info()

        return self

    async def update_data(self, data: Any) -> Any:
        if "pageId" not in data:
            data["pageId"] = self.page_id
        return await self.wiki.api(Endpoint.Article.get_endpoint_route(self.page_id, Method.PUT), json=data)

    @property
    def title(self) -> str | None:
        if not self._raw_data:
            return None
        return self._raw_data["title"]

    @property
    def source(self) -> str | None:
        if not self._raw_data:
            return None
        return self._raw_data["source"]

    @property
    def name(self) -> str:
        return self.page_id

    @property
    def tags(self) -> List[str] | None:
        if not self._raw_data:
            return None
        return self._raw_data["tags"]
    
    @property
    def history(self) -> List[LogEntry] | None:
        if not self._article_log:
            return None
        return [LogEntry.from_dict(entry) for entry in deepcopy(self._article_log["entries"])]

    @cached_property
    def created_at(self) -> datetime | None:
        if not self.history:
            return None
        return self.history[-1].createdAt
    
    @property
    def last_source_edit(self) -> datetime | None:
        if not self.history:
            return None
        return self.filter_history(LogEntryType.Source)[0].createdAt
    
    @property
    def last_modify(self) -> datetime | None:
        if not self.history:
            return None
        return self.history[0].createdAt

    @cached_property
    def author(self) -> User | None:
        if not self.history:
            return None
        return self.history[-1].user

    @property
    def votes(self) -> List[Vote] | None:
        if not self._votes_info:
            return None
        return [Vote.from_dict(vote) for vote in self._votes_info["votes"]]
    
    @property
    def votes_count(self) -> int | None:
        if not self._votes_info:
            return None
        return len(self.votes)
    
    @property
    def rating(self) -> float | None:
        if not self._votes_info:
            return None
        return self._votes_info["rating"]

    @property
    def popularity(self) -> int | None:
        if not self._votes_info:
            return None
        return self._votes_info["popularity"]
    
    async def filter_history(self, type: Optional[LogEntryType | str]=None, lazy: bool=True) -> List[LogEntry]:
        await lazy_async(lazy, self.history is None, self.get_article_log)

        if isinstance(type, LogEntryType):
            type = type.value

        return [entry for entry in self.history if entry.type == type]
    
    async def _get_raw_data(self) -> Any:
        self._raw_data = await self.wiki.api(Endpoint.Article.get_endpoint_route(self.page_id))
        return self._raw_data
    
    async def get_article_log(self):
        self._article_log = await self.wiki.api(Endpoint.ArticleLog.get_endpoint_route(self.page_id), params={"all": "true"})
        return self._article_log
    
    async def get_votes_info(self):
        self._votes_info = await self.wiki.module(Module.Rate, "get_votes", pageId=self.page_id)
        return self._votes_info
    
    async def get_last_category_move(self, lazy: bool=True):
        await lazy_async(lazy, self.history is None, self.get_article_log)

        for entry in reversed(await self.filter_history(LogEntryType.Name)):
            new_namecategory = page_category(entry.meta["name"])
            if new_namecategory == page_category(self.name) and \
               new_namecategory != page_category(entry.meta["prev_name"]):
                return entry
            
        return self.history[-1]
    
    async def get_tag_date(self, tag: str, lazy: bool=True) -> datetime | None:
        await lazy_async(lazy, self.tags is None, self._get_raw_data)

        normalized_tag = normalize_tag(tag)

        if normalized_tag not in self.tags:
            return None
        
        for entry in reversed(await self.filter_history(LogEntryType.Tags)):
            if normalized_tag in [tag_entry["name"] for tag_entry in entry.meta["added_tags"]]:
                return entry.createdAt
            
        return None
    
    async def set_tags(self, tags: List[str]):
        await self.update_data({"tags": tags})
    
    async def add_tags(self, tags: List[str], lazy: bool=True):
        await lazy_async(lazy, self.tags is None, self._get_raw_data)

        new_tags = self.tags
        new_tags.extend(map(normalize_tag, tags))
        await self.set_tags(list(set(new_tags)))
    
    async def remove_tags(self, tags: List[str], lazy: bool=True) -> List[str]:
        await lazy_async(lazy, self.tags is None, self._get_raw_data)

        new_tags = self.tags
        removed_tags = []

        for tag in tags:
            normalized_tag = normalize_tag(tag)
            if normalized_tag in new_tags:
                new_tags.remove(normalized_tag)
                removed_tags.append(normalized_tag)
        await self.set_tags(new_tags)
        return removed_tags

    async def update_tags(self, add_tags: List[str]=None, remove_tags: List[str]=None, lazy: bool=True):
        await lazy_async(lazy, self.tags is None, self._get_raw_data)

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

    async def delete_page(self):
        await self.wiki.api(Endpoint.Article.get_endpoint_route(self.page_id, Method.DELETE))

    async def rename(self, new_id: str, retries: int=10):
        try:
            await self.update_data({"pageId": new_id})
            self.page_id = new_id
        except client_exceptions.ClientResponseError:
            if retries:
                await self.rename(f"{new_id}_{random_string(6)}", retries-1)

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
    def __init__(self, wiki_base: str, token: str=None):
        self.wiki_base = URL(wiki_base)
        self.token = token
        self._logger = logging.getLogger()

    async def api(self, endpoint: Endpoint | Route, *args, **kwargs) -> Any:
        if "headers" not in kwargs:
            kwargs["headers"] = {}

        if isinstance(endpoint, Endpoint) :
            route = endpoint.value
        else:
            route = endpoint

        kwargs["headers"].update({
            "Authorization": f"Bearer {self.token}",
        })
        
        self._logger.debug(f"API call to endpoint: {self.wiki_base / "api/" / route.endpoint} with args: {args} and kwargs: {kwargs}")

        async with request(route.method.name, self.wiki_base / "api/" / route.endpoint, *args, **kwargs) as resp:
            # self._logger.debug(resp.request_info)
            resp.raise_for_status()
            return await resp.json()
        
    async def get_page(self, page_id: str, lazy: bool=True) -> Page:
        if lazy:
            return Page(self, page_id)
        return await Page(self, page_id).fetch()
        
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