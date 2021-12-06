"""Module for working with Wikidot
"""
from core.utils import Singleton

from typing import Optional, Iterator, List
import pyscp


class Page(pyscp.wikidot.Page):
    """Wikidot page class
    """
    def delete_page(self):
        """Delete page
        """
        self._action("deletePage")


class Thread(pyscp.wikidot.Thread):
    """Wikidot thread class
    """
    pass


class Wiki(pyscp.wikidot.Wiki):
    """Wikidot wiki class
    """
    Page = Page
    Thread = Thread

    def __init__(self, site):
        super(Wiki, self).__init__(site)
        self.wiki = site


class Wikidot(metaclass=Singleton):
    """Wikidot singleton class
    """

    def __init__(self, sites: Optional[List[str]] = None):
        """Initializing Wikidot class

        Args:
            sites (Optional[List[str]]): List of wikidot sites
        """
        self.req = pyscp.wikidot.InsistentRequest()
        self._cookies = "wikidot_token7=123456;"

        self._sites = sites if sites else []

    def auth(self, username: str, password: str):
        """Auth to wikidot by credentials

        Args:
            username (str): Username
            password (str): Password
        """
        login = self.req.post(
            "https://www.wikidot.com/default--flow/login__LoginPopupScreen",
            data=dict(
                login=username, password=password, action="Login2Action", event="login"
            ),
        )
        self._cookies += f"WIKIDOT_SESSION_ID={login.cookies['WIKIDOT_SESSION_ID']};"

    @property
    def wikis(self) -> Iterator[Wiki]:
        """Get wikis from config

        Yields:
            Wiki: Wiki instance
        """
        for site in self._sites:
            yield self.get_wiki(site)

    def get_wiki(self, site: str) -> Wiki:
        """Get wiki by site name

        Args:
            site (str): Wikidot site name

        Returns:
            Wiki: Wiki instance
        """
        wiki = Wiki(site)
        if self._cookies:
            wiki.cookies = self._cookies

        return wiki
