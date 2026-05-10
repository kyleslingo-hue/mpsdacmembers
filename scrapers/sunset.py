"""
Sabbath sunset times for Portland, CT via the free sunrise-sunset.org API.

Returns the Friday sunset (Sabbath begins) and Saturday sunset (Sabbath ends)
for the upcoming Sabbath week, in Eastern time.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Portland, CT
LAT = 41.5548
LNG = -72.6414

API_URL = "https://api.sunrise-sunset.org/json"


@dataclass
class SabbathTimes:
    friday_date: date
    saturday_date: date
    begins: str   # "7:52 PM" style
    ends: str


def _fetch_sunset(for_date: date) -> Optional[datetime]:
    try:
        resp = requests.get(
            API_URL,
            params={"lat": LAT, "lng": LNG, "date": for_date.isoformat(), "formatted": 0},
            timeout=10,
        )
        resp.raise_for_status()
        sunset_str = resp.json()["results"]["sunset"]
        return datetime.fromisoformat(sunset_str)
    except Exception as e:
        logger.warning(f"[Sunset] Failed to fetch for {for_date}: {e}")
        return None


_EASTERN = timezone(timedelta(hours=-5))  # ET standard; DST handled below


def _fmt(dt: datetime) -> str:
    # Determine Eastern offset: EDT (UTC-4) Mar–Nov, EST (UTC-5) otherwise
    month = dt.month
    offset = timedelta(hours=-4) if 3 <= month <= 11 else timedelta(hours=-5)
    eastern = timezone(offset)
    local = dt.astimezone(eastern)
    return local.strftime("%-I:%M %p")


def get_sabbath_times(next_sabbath: date) -> Optional[SabbathTimes]:
    """
    next_sabbath is the upcoming Saturday. Returns sunset on Friday before it
    (Sabbath begins) and sunset on that Saturday (Sabbath ends).
    """
    friday = next_sabbath - timedelta(days=1)

    begins_dt = _fetch_sunset(friday)
    ends_dt = _fetch_sunset(next_sabbath)

    if not begins_dt or not ends_dt:
        return None

    return SabbathTimes(
        friday_date=friday,
        saturday_date=next_sabbath,
        begins=_fmt(begins_dt),
        ends=_fmt(ends_dt),
    )
