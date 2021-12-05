from core.utils import Singleton

from typing import Optional, Iterator, List
import pyscp


class Page(pyscp.wikidot.Page):
    def delete_page(self):
        self._action("deletePage")


class Thread(pyscp.wikidot.Thread):
    pass


class Wiki(pyscp.wikidot.Wiki):
    Page = Page
    Thread = Thread

    def __init__(self, site):
        super(Wiki, self).__init__(site)
        self.wiki = site


class Wikidot(metaclass=Singleton):
    def __init__(self, sites: Optional[List[str]] = None):
        self.req = pyscp.wikidot.InsistentRequest()
        self._cookies = "wikidot_token7=123456;"

        self._sites = sites if sites else []

    def auth(self, username: str, password: str):
        login = self.req.post(
            "https://www.wikidot.com/default--flow/login__LoginPopupScreen",
            data=dict(
                login=username, password=password, action="Login2Action", event="login"
            ),
        )
        self._cookies += f"WIKIDOT_SESSION_ID={login.cookies['WIKIDOT_SESSION_ID']};"

    @property
    def wikis(self) -> Iterator[Wiki]:
        for site in self._sites:
            yield self.get_wiki(site)

    def get_wiki(self, site: str) -> Wiki:
        wiki = Wiki(site)
        if self._cookies:
            wiki.cookies = self._cookies

        return wiki
