"""
Speaker calendar integration.

Attempts to download the SharePoint-hosted Excel file.
If the file is shared publicly (Anyone with link = view), it will download
directly. Otherwise falls back to a local CSV/XLSX export named
`speaker_calendar.xlsx` or `speaker_calendar.csv` in the project root.
"""

import io
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

SHAREPOINT_URL = (
    "https://3angelschurch-my.sharepoint.com/:x:/p/scott_tompkins/"
    "IQDiaZkbtrIFQadsVI3Pt8uaAYX2t0VUdyJP1VSRAUzjAxw"
)
# SharePoint direct-download suffix
DOWNLOAD_URL = SHAREPOINT_URL + "?download=1"

LOCAL_FALLBACKS = [
    Path(__file__).parent.parent / "speaker_calendar.xlsx",
    Path(__file__).parent.parent / "speaker_calendar.csv",
]


@dataclass
class SpeakerEntry:
    date_str: str
    speaker: str
    sermon_title: str = ""
    notes: str = ""
    parsed_date: Optional[date] = None

    def is_future(self) -> bool:
        if self.parsed_date is None:
            return True
        return self.parsed_date >= date.today()


class SpeakerCalendar:
    def __init__(self):
        self.entries: List[SpeakerEntry] = []

    def fetch(self, count: int = 5) -> List[SpeakerEntry]:
        data = self._try_sharepoint() or self._try_local()
        if data is None:
            logger.warning(
                "Speaker calendar: could not download or find local file. "
                "Export the calendar to speaker_calendar.xlsx in the project root."
            )
            return []
        self.entries = self._parse(data)
        today = date.today()
        results = [
            e for e in self.entries
            if e.parsed_date is not None and e.parsed_date > today
        ]
        return results[:count]

    # ------------------------------------------------------------------
    def _try_sharepoint(self) -> Optional[bytes]:
        try:
            resp = requests.get(DOWNLOAD_URL, timeout=15, allow_redirects=True)
            ct = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and (
                "spreadsheet" in ct or "excel" in ct or "octet-stream" in ct
            ):
                logger.info("Speaker calendar: downloaded from SharePoint.")
                return resp.content
            logger.info(
                f"SharePoint returned {resp.status_code} / {ct[:60]} — "
                "file may require login."
            )
        except requests.RequestException as e:
            logger.warning(f"SharePoint download failed: {e}")
        return None

    def _try_local(self) -> Optional[bytes]:
        for path in LOCAL_FALLBACKS:
            if path.exists():
                logger.info(f"Speaker calendar: using local file {path.name}")
                return path.read_bytes()
        return None

    def _parse(self, data: bytes) -> List[SpeakerEntry]:
        # Try Excel first, then CSV
        try:
            return self._parse_excel(data)
        except Exception:
            pass
        try:
            return self._parse_csv(data)
        except Exception as e:
            logger.warning(f"Speaker calendar parse failed: {e}")
            return []

    def _parse_excel(self, data: bytes) -> List[SpeakerEntry]:
        import pandas as pd

        df = pd.read_excel(io.BytesIO(data), header=None)
        return self._dataframe_to_entries(df)

    def _parse_csv(self, data: bytes) -> List[SpeakerEntry]:
        import io as _io

        import pandas as pd

        df = pd.read_csv(_io.StringIO(data.decode("utf-8", errors="replace")), header=None)
        return self._dataframe_to_entries(df)

    def _dataframe_to_entries(self, df) -> List[SpeakerEntry]:
        from dateutil import parser as du

        entries: List[SpeakerEntry] = []

        # Find the header row — it will contain our church name or "Sabbath"
        header_row_idx = 0
        for i, row in df.iterrows():
            vals = [str(v).lower() for v in row.values]
            if any(
                "middletown" in v or "sabbath" in v or "date" in v or "speaker" in v
                for v in vals
            ):
                header_row_idx = i
                break

        # Capture the actual column headers from that row
        headers = [str(v).strip() for v in df.iloc[header_row_idx].values]
        data_df = df.iloc[header_row_idx + 1 :].reset_index(drop=True)
        data_df.columns = range(len(data_df.columns))

        # Map columns by header name
        # Date column: header contains "sabbath" or "date", or first column with date values
        date_col = None
        speaker_col = None

        for idx, h in enumerate(headers):
            hl = h.lower()
            if "sabbath" in hl or "date" in hl:
                date_col = idx
                break

        # Prefer a column whose header mentions "middletown" or "portland"
        for idx, h in enumerate(headers):
            if idx == date_col:
                continue
            hl = h.lower()
            if "middletown" in hl or "portland" in hl:
                speaker_col = idx
                break

        # Fallback: first non-date text column
        if speaker_col is None:
            for idx in range(len(headers)):
                if idx != date_col:
                    speaker_col = idx
                    break

        if date_col is None or speaker_col is None:
            logger.warning("Speaker calendar: could not identify required columns.")
            return entries

        logger.info(
            f"Speaker calendar columns — date: '{headers[date_col]}', "
            f"speaker: '{headers[speaker_col]}'"
        )

        def clean(val) -> str:
            s = str(val).strip()
            return "" if s.lower() in ("nan", "none", "nat", "nattype") else s

        def fmt_date(val) -> str:
            s = str(val).strip()
            if s.lower() in ("nan", "none", "nat", "nattype", ""):
                return ""
            try:
                return du.parse(s, fuzzy=True).strftime("%B %-d, %Y")
            except Exception:
                return s

        for _, row in data_df.iterrows():
            date_val = fmt_date(row.get(date_col, ""))
            if not date_val:
                continue
            speaker = clean(row.get(speaker_col, ""))
            if not speaker:
                continue

            parsed = None
            try:
                parsed = du.parse(date_val, fuzzy=True).date()
            except Exception:
                pass

            entries.append(SpeakerEntry(
                date_str=date_val,
                speaker=speaker,
                parsed_date=parsed,
            ))
        return entries
