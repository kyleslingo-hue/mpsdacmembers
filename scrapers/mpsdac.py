"""
Scraper for mpsdac.org church events via Firebase Firestore.

The site uses Firestore with anonymous auth. We sign in anonymously with the
public API key (same as the browser JS does), then query the churchEvents
collection for published future events.
"""

import logging
from datetime import date, datetime, timezone
from typing import List, Optional

import requests

from .base import Event

logger = logging.getLogger(__name__)

API_KEY = "AIzaSyAkq5iZf7UOGgbpjuJnnR7JZZyTHb40Xks"
PROJECT = "mpsdac-534d5"

SIGN_IN_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
)
QUERY_URL = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
    "/databases/(default)/documents:runQuery"
)

QUERY_BODY = {
    "structuredQuery": {
        "from": [{"collectionId": "churchEvents"}],
        "where": {
            "fieldFilter": {
                "field": {"fieldPath": "isPublished"},
                "op": "EQUAL",
                "value": {"booleanValue": True},
            }
        },
        "limit": 100,
    }
}


class MPSDACscraper:
    SOURCE_NAME = "MPSDAC"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def scrape(self) -> List[Event]:
        token = self._get_token()
        if not token:
            logger.warning("[MPSDAC] Could not obtain Firebase auth token.")
            return []

        try:
            resp = self.session.post(
                QUERY_URL,
                json=QUERY_BODY,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[MPSDAC] Firestore query failed: {e}")
            return []

        events = []
        for item in resp.json():
            doc = item.get("document")
            if not doc:
                continue
            event = self._parse_doc(doc)
            if event and event.is_future():
                events.append(event)

        return events

    # ------------------------------------------------------------------

    def _get_token(self) -> Optional[str]:
        try:
            resp = self.session.post(
                SIGN_IN_URL,
                json={"returnSecureToken": True},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("idToken")
        except requests.RequestException as e:
            logger.warning(f"[MPSDAC] Firebase sign-in failed: {e}")
            return None

    def _parse_doc(self, doc: dict) -> Optional[Event]:
        fields = doc.get("fields", {})

        def str_val(key: str) -> str:
            v = fields.get(key, {})
            return str(list(v.values())[0]).strip() if v else ""

        def ts_val(key: str) -> Optional[datetime]:
            v = fields.get(key, {})
            raw = list(v.values())[0] if v else None
            if not raw or str(raw).lower() in ("none", "null", ""):
                return None
            try:
                # Firestore timestamps come as ISO strings ending in Z
                s = str(raw).replace("Z", "+00:00")
                return datetime.fromisoformat(s)
            except Exception:
                return None

        title = str_val("title")
        if not title:
            return None

        start_dt = ts_val("startDate")
        end_dt = ts_val("endDate")

        # Format date string for display (convert UTC → local date)
        if start_dt:
            local_date = start_dt.astimezone().date()
            date_str = start_dt.astimezone().strftime("%A, %B %-d, %Y")
            if start_dt.astimezone().hour or start_dt.astimezone().minute:
                date_str += start_dt.astimezone().strftime(" at %-I:%M %p")
            if end_dt:
                end_local = end_dt.astimezone().date()
                if end_local != local_date:
                    date_str += " – " + end_dt.astimezone().strftime("%B %-d, %Y")
        else:
            local_date = None
            date_str = ""

        desc = str_val("eventDescription")
        # Strip any embedded URLs from description (they're pulled out separately)
        import re
        url_match = re.search(r"https?://\S+", desc)
        event_url = url_match.group(0).rstrip(".,;!?)") if url_match else ""
        desc_clean = re.sub(r"https?://\S+", "", desc).strip()

        category = str_val("category") or "General"

        e = Event(
            title=title,
            date_str=date_str,
            source=self.SOURCE_NAME,
            description=desc_clean,
            location=str_val("location"),
            url=event_url,
            category=category,
        )
        e.parsed_date = local_date
        if end_dt:
            end_local = end_dt.astimezone().date()
            if end_local != local_date:
                e.parsed_end_date = end_local
        return e
