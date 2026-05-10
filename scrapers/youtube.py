"""
YouTube scraper for the MPSDAC channel.

Scrapes /videos and /streams tabs to get the most recent upload and most
recent live stream. Uses the YouTube oembed API for titles — no API key needed.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

CHANNEL_VIDEOS_URL = "https://www.youtube.com/@mpsdac/videos"
CHANNEL_STREAMS_URL = "https://www.youtube.com/@mpsdac/streams"
OEMBED_URL = "https://www.youtube.com/oembed"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    url: str
    channel: str = "Middletown Portland SDA Church"

    @property
    def thumbnail_url(self) -> str:
        return f"https://img.youtube.com/vi/{self.video_id}/hqdefault.jpg"


@dataclass
class MediaBundle:
    latest_video: Optional[YouTubeVideo]
    latest_stream: Optional[YouTubeVideo]


class YouTubeScraper:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_media(self) -> MediaBundle:
        latest_video = self._first_from(CHANNEL_VIDEOS_URL)
        latest_stream = self._first_from(CHANNEL_STREAMS_URL)
        return MediaBundle(latest_video=latest_video, latest_stream=latest_stream)

    # ------------------------------------------------------------------

    def _first_from(self, url: str) -> Optional[YouTubeVideo]:
        ids = self._get_video_ids(url)
        if not ids:
            return None
        return self._fetch_video_info(ids[0])

    def _get_video_ids(self, url: str) -> List[str]:
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[YouTube] Fetch failed ({url}): {e}")
            return []

        return list(dict.fromkeys(
            re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', resp.text)
        ))

    def _fetch_video_info(self, video_id: str) -> Optional[YouTubeVideo]:
        try:
            resp = self.session.get(
                OEMBED_URL,
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return YouTubeVideo(
                video_id=video_id,
                title=data.get("title", ""),
                url=f"https://youtu.be/{video_id}",
                channel=data.get("author_name", "Middletown Portland SDA Church"),
            )
        except requests.RequestException as e:
            logger.warning(f"[YouTube] oembed failed for {video_id}: {e}")
            return None
