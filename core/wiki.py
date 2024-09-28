"""Module for working with Wiki
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from functools import cached_property
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
import inspect
import requests


ENDPOINTS = {
    "MODULES": "modules",
    "ARTICLE": "articles/{}",
    "ARTICLE_LOGS": "articles/{}/log",
}


class Method(Enum):
    GET = auto()
    POST = auto()
    PUT = auto()
    DELETE = auto()


class APIData:
    @classmethod
    def from_dict(cls, parameters):
        allowed_parameters = inspect.signature(cls).parameters
        filtered_parameters = {k: v for k, v in parameters.items() if k in allowed_parameters}
        return cls(**filtered_parameters)


@dataclass
class Route(APIData):
    endpoint: str
    method: Method = Method.GET


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


@dataclass
class LogEntry(APIData):
    revNumber: int
    user: User
    comment: str
    createdAt: datetime
    type: str
    meta: Dict[str, Any]

    @classmethod
    def from_dict(cls, parameters) -> List[LogEntry]:
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

    def __repr__(self) -> str:
        return "{}.{}({}, {})".format(
            self.__module__, self.__class__.__name__, repr(self.wiki), repr(self.page_id)
        )

    def _api(self, *args, **kwargs) -> Any:
        return self.wiki._api(*args, **kwargs)

    def _module(self, *args, **kwargs) -> Any:
        return self.wiki._module(*args, **kwargs)

    def _get_endpoint(self, name: str) -> str:
        return ENDPOINTS[name].format(self.page_id)

    @cached_property
    def _pdata(self) -> Any:
        return self._api(Route(self._get_endpoint("ARTICLE")))

    def _update_data(self, data: Any) -> Any:
        data["pageId"] = self.page_id
        return self._api(Route(self._get_endpoint("ARTICLE"), Method.PUT), json=data)

    @property
    def title(self) -> str:
        return self._pdata["title"]

    @property
    def source(self) -> str:
        return self._pdata["source"]

    @property
    def name(self) -> str:
        return self.page_id

    @property
    def tags(self) -> List[str]:
        return self._pdata["tags"]

    def set_tags(self, tags: List[str]):
        return self._update_data({"tags": tags})

    def delete_page(self):
        return self._api(Route(self._get_endpoint("ARTICLE"), Method.DELETE))

    def rename(self, new_id: str):
        return self._update_data({"pageId": new_id})

    @cached_property
    def history(self) -> List[LogEntry]:
        entries = self._api(Route(self._get_endpoint("ARTICLE_LOGS")), params={"all": "true"})["entries"]
        return [LogEntry.from_dict(entry) for entry in entries]

    @property
    def created(self) -> datetime:
        return self.history[-1].createdAt

    @property
    def author(self) -> User:
        return self.history[-1].user

    @property
    def rating(self) -> float:
        return self._module("rate", "get_rating", pageId=self.page_id)["rating"]

    @property
    def votes(self) -> List[Vote]:
        return [Vote.from_dict(vote) for vote in self._module("rate", "get_votes", pageId=self.page_id)["votes"]]

    @property
    def popularity(self) -> int:
        return self._module("rate", "get_votes", pageId=self.page_id)["popularity"]

    @property
    def thread(self) -> Thread:
        return Thread(self.wiki, self._module("forumthread", "for_article", pageId=self.page_id)["threadId"], self)


class Thread:
    def __init__(self, wiki: Wiki, thread_id: str, page: Optional[Page] = None):
        self.wiki = wiki
        self.thread_id = thread_id
        self.page = page

    def __repr__(self) -> str:
        return "{}.{}({}, {}, page={})".format(
            self.__module__, self.__class__.__name__, repr(self.wiki), repr(self.thread_id), repr(self.page)
        )

    def new_post(self, source: str, title: Optional[str] = None):
        params = {
            "threadid": self.thread_id,
            "name": title,
            "source": source,
        }
        return self.wiki._module("forumnewpost", "submit", params=params)


class Wiki:
    def __init__(self, site: str, authkey: Optional[str] = None):
        self.site = site
        self.authkey = authkey

    def __repr__(self) -> str:
        return "{}.{}({})".format(
            self.__module__, self.__class__.__name__, repr(self.site)
        )

    def auth(self, authkey: str) -> Wiki:
        self.authkey = authkey
        return self

    def _build_link(self, endpoint: str) -> str:
        return f"{self.site}/api/{endpoint}"

    def _api(self, route: Route, *args, **kwargs) -> Any:
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"].update({
            "Authorization": f"Bearer {self.authkey}",
            }
        )

        req = requests.request(route.method.name, self._build_link(route.endpoint), *args, **kwargs)
        req.raise_for_status()

        return req.json()

    def _module(self, name: str, method: str, **kwargs) -> Any:
        data = {"module": name, "method": method}
        data.update(kwargs)
        return self._api(Route(ENDPOINTS["MODULES"], Method.POST), json=data)

    def _raw_list_pages(self, **params) -> Any:
        return self._module("listpages", "get", params=params)

    def list_pages(self, **params) -> List[Page]:
        return [self.get(page_id) for page_id in self._raw_list_pages(**params)["pages"]]

    def get(self, page_id: str) -> Page:
        return Page(self, page_id)


if __name__ == "__main__":
    wiki = Wiki("http://localhost:8000").auth("yLVKk1pdobeUYT6C0cdbAE$JuoG3TRZKcSFZr7WusfPCfRDzWX2XOv8qYHqQ/q8s/Y=")
    print()
