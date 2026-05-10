"""Base scraper with shared HTTP logic and event normalization."""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 15


@dataclass
class Event:
    title: str
    date_str: str
    source: str
    description: str = ""
    location: str = ""
    url: str = ""
    category: str = "General"
    parsed_date: Optional[date] = field(default=None, repr=False)
    parsed_end_date: Optional[date] = field(default=None, repr=False)

    @property
    def uid(self) -> str:
        raw = f"{self.title.lower().strip()}{self.date_str}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def is_future(self) -> bool:
        if self.parsed_date is None:
            return True  # keep if we can't parse
        return self.parsed_date > date.today()


class BaseScraper:
    SOURCE_NAME: str = "Unknown"
    BASE_URL: str = ""

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def get(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        try:
            resp = self.session.get(url, timeout=TIMEOUT, **kwargs)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            logger.warning(f"[{self.SOURCE_NAME}] Failed to fetch {url}: {e}")
            return None

    def scrape(self) -> List[Event]:
        raise NotImplementedError

    def _try_parse_date(self, text: str) -> Optional[date]:
        from dateutil import parser as du_parser
        clean = text.strip()
        if not clean:
            return None
        try:
            return du_parser.parse(clean, fuzzy=True).date()
        except Exception:
            return None
