#!/usr/bin/env python3
"""
Middletown Portland SDA Church — Public Member Portal
Standalone Flask app for deployment on Render (or any WSGI host).

Run locally:  python3 portal_app.py
Production:   gunicorn portal_app:app
"""

import sys
import time
from datetime import date
from pathlib import Path

from flask import Flask, render_template

sys.path.insert(0, str(Path(__file__).parent))

from scrapers import MPSDACscraper, SpeakerCalendar, YouTubeScraper, get_sabbath_times
from email_generator import _next_sabbath

# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent

app = Flask(__name__, template_folder="templates/gui")

# ---------------------------------------------------------------------------
# Cache — refresh every 30 minutes so cold-start is rare and scraper load is low
# ---------------------------------------------------------------------------

_cache: dict = {"data": None, "fetched_at": 0.0}
CACHE_TTL = 1800  # seconds


def _fetch() -> dict:
    speakers, events, media, sabbath_times = [], [], None, None

    try:
        speakers = SpeakerCalendar().fetch(count=5)
    except Exception:
        pass

    try:
        events = MPSDACscraper().scrape()
    except Exception:
        pass

    try:
        media = YouTubeScraper().fetch_media()
    except Exception:
        pass

    try:
        sabbath_times = get_sabbath_times(_next_sabbath())
    except Exception:
        pass

    next_sab = _next_sabbath()

    return {
        "speakers": [
            {"date": s.date_str, "speaker": s.speaker, "sermon": s.sermon_title}
            for s in speakers
        ],
        "events": [
            {
                "title": e.title,
                "date": e.date_str,
                "day": e.parsed_date.strftime("%-d") if e.parsed_date else "—",
                "month": e.parsed_date.strftime("%b").upper() if e.parsed_date else "",
                "end_day": e.parsed_end_date.strftime("%-d") if e.parsed_end_date else None,
                "end_month": e.parsed_end_date.strftime("%b").upper() if e.parsed_end_date else None,
                "location": e.location,
                "description": e.description or "",
                "category": e.category,
                "url": e.url,
            }
            for e in events
        ],
        "media": {
            "stream": {
                "title": media.latest_stream.title,
                "url": media.latest_stream.url,
                "thumb": media.latest_stream.thumbnail_url,
            } if media and media.latest_stream else None,
            "video": {
                "title": media.latest_video.title,
                "url": media.latest_video.url,
                "thumb": media.latest_video.thumbnail_url,
            } if media and media.latest_video else None,
        },
        "sabbath": {
            "date": next_sab.strftime("%A, %B %-d, %Y"),
            "begins": sabbath_times.begins if sabbath_times else "",
            "ends": sabbath_times.ends if sabbath_times else "",
        },
    }


def get_data() -> dict:
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]
    data = _fetch()
    _cache["data"] = data
    _cache["fetched_at"] = now
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/portal")
def portal():
    return render_template("portal.html", data=get_data())


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  MPSDAC Member Portal — http://localhost:5051\n")
    app.run(debug=False, port=5051)
