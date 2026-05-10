"""Build email body (plain text + HTML) from collected data."""

import urllib.parse
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from scrapers.base import Event
from scrapers.calendar import SpeakerEntry
from scrapers.youtube import YouTubeVideo, MediaBundle
from scrapers.sunset import SabbathTimes

TO = "kslingo@middletownportlandsda.org"
SUBJECT = "Weekly SDA Events & Church Communications"

OUTPUT_DIR = Path(__file__).parent / "output"
TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _next_sabbath() -> date:
    today = date.today()
    days_ahead = (5 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # today is Sabbath — point to next week
    return today + timedelta(days=days_ahead)


def _format_date(d: Optional[date], fallback: str = "") -> str:
    if d:
        return d.strftime("%A, %B %-d, %Y")
    return fallback


# ---------------------------------------------------------------------------
# Speaker rendering
# ---------------------------------------------------------------------------

def _speakers_html(entries: List[SpeakerEntry]) -> str:
    if not entries:
        return '<p class="no-events">Speaker schedule not available.</p>'
    rows = []
    for s in entries:
        sermon = (
            f'<div class="speaker-sermon">{s.sermon_title}</div>'
            if s.sermon_title else ""
        )
        rows.append(f"""
        <div class="speaker-row">
          <div class="speaker-date">{s.date_str}</div>
          <div class="speaker-divider"></div>
          <div>
            <div class="speaker-name">{s.speaker}</div>
            {sermon}
          </div>
        </div>""")
    return "\n".join(rows)


def _speakers_plain(entries: List[SpeakerEntry]) -> str:
    if not entries:
        return "  (Speaker schedule not available)\n"
    lines = []
    for s in entries:
        line = f"  {s.date_str:<16} {s.speaker}"
        if s.sermon_title:
            line += f' — "{s.sermon_title}"'
        lines.append(line)
    return "\n".join(lines) + "\n"


def _speakers_table_html(entries: List[SpeakerEntry]) -> str:
    if not entries:
        return '<p class="no-events">Speaker schedule not available.</p>'
    rows = [
        f"<tr><td>{s.date_str}</td><td>{s.speaker}</td><td><em>{s.sermon_title}</em></td></tr>"
        for s in entries
    ]
    return (
        '<table class="speaker-table">'
        "<thead><tr><th>Date</th><th>Speaker</th><th>Sermon Title</th></tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody></table>"
    )


# ---------------------------------------------------------------------------
# Event rendering
# ---------------------------------------------------------------------------

def _event_card_html(e: Event) -> str:
    # Day/month from parsed_date, fallback to raw string
    if e.parsed_date:
        day = e.parsed_date.strftime("%-d")
        month = e.parsed_date.strftime("%b").upper()
    else:
        day = "—"
        month = ""

    desc_html = (
        f'<div class="event-desc-text">{e.desc_short}</div>'
        if e.desc_short else ""
    )
    loc_html = (
        f'<div class="event-meta">📍 {e.location}</div>'
        if e.location else ""
    )
    link_html = (
        f'<a class="event-link-btn" href="{e.url}">More info →</a>'
        if e.url else ""
    )
    cat = e.category or "Event"

    return f"""
    <div class="event-card">
      <div class="event-date-block">
        <div class="day">{day}</div>
        <div class="month">{month}</div>
      </div>
      <div class="event-divider"></div>
      <div class="event-body">
        <span class="event-badge">{cat}</span>
        <div class="event-title-text">{e.title}</div>
        {loc_html}
        {desc_html}
        {link_html}
      </div>
    </div>"""


def _event_html_block(events: List[Event]) -> str:
    if not events:
        return '<p class="no-events">No upcoming events.</p>'
    return "\n".join(_event_card_html(e) for e in events)


def _event_plain_block(events: List[Event], indent: str = "  ") -> str:
    if not events:
        return f"{indent}(No upcoming events)\n"
    lines = []
    for e in events:
        lines.append(f"{indent}• {e.title}")
        if e.date_str:
            lines.append(f"{indent}  {e.date_str}")
        if e.location:
            lines.append(f"{indent}  {e.location}")
        if e.desc_short:
            lines.append(f"{indent}  {e.desc_short}")
        if e.url:
            lines.append(f"{indent}  {e.url}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Media rendering
# ---------------------------------------------------------------------------

def _video_card_html(video: Optional[YouTubeVideo], label: str) -> str:
    if not video:
        return ""
    return f"""
    <a class="media-card" href="{video.url}" target="_blank">
      <div class="media-thumb">
        <img src="{video.thumbnail_url}" alt="{video.title}">
        <div class="play-button">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 5v14l11-7z"/>
          </svg>
        </div>
      </div>
      <div class="media-body">
        <div class="media-type">{label}</div>
        <div class="media-title">{video.title}</div>
        <div class="media-link">youtube.com/@mpsdac</div>
      </div>
    </a>"""


def _media_html(media: Optional[MediaBundle]) -> str:
    if not media or (not media.latest_stream and not media.latest_video):
        return '<p class="no-events">No media available yet — check back after service.</p>'
    return (
        '<div class="media-grid">'
        + _video_card_html(media.latest_stream, "Live Stream")
        + _video_card_html(media.latest_video, "Latest Upload")
        + "</div>"
    )


def _media_plain(media: Optional[MediaBundle]) -> str:
    if not media:
        return "  (No media available yet)\n"
    lines = []
    if media.latest_stream:
        lines += [f"  Live Stream: {media.latest_stream.title}", f"  {media.latest_stream.url}", ""]
    if media.latest_video:
        lines += [f"  Latest Upload: {media.latest_video.title}", f"  {media.latest_video.url}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sunset rendering
# ---------------------------------------------------------------------------

def _sunset_row_html(st: Optional[SabbathTimes]) -> str:
    if not st:
        return ""
    return f"""
    <div class="sunset-row">
      <div class="sunset-item">
        <span class="sun-icon">🌇</span>
        <span class="sun-label">Sabbath begins (Fri)</span>
        <span class="sun-time">{st.begins}</span>
      </div>
      <div class="sunset-item">
        <span class="sun-icon">🌆</span>
        <span class="sun-label">Sabbath ends (Sat)</span>
        <span class="sun-time">{st.ends}</span>
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# EmailGenerator
# ---------------------------------------------------------------------------

class EmailGenerator:
    def __init__(
        self,
        speakers: List[SpeakerEntry],
        events: List[Event],
        media: Optional[MediaBundle] = None,
        sabbath_times: Optional[SabbathTimes] = None,
    ):
        self.speakers = speakers
        self.events = events
        self.media = media
        self.sabbath_times = sabbath_times

        self.youth_events = [e for e in events if e.category == "Youth"]
        self.young_adult_events = [e for e in events if e.category == "Young Adults"]
        self.general_events = [
            e for e in events if e.category not in ("Youth", "Young Adults")
        ]

        self.sabbath = _next_sabbath()
        self.today = date.today()
        self.days_until = (self.sabbath - self.today).days

    # ---- HTML email ----------------------------------------------------------

    def build_html(self) -> str:
        template = (TEMPLATE_DIR / "email_template.html").read_text()

        replacements = {
            "{{generated_date}}": self.today.strftime("%B %-d, %Y"),
            "{{next_sabbath}}": _format_date(self.sabbath),
            "{{days_until_sabbath}}": str(self.days_until),
            "{{sunset_row}}": _sunset_row_html(self.sabbath_times),
            "{{speakers_section}}": _speakers_html(self.speakers),
            "{{media_section}}": _media_html(self.media),
            "{{church_events_section}}": _event_html_block(self.general_events),
            "{{youth_events_section}}": _event_html_block(self.youth_events),
            "{{young_adults_section}}": _event_html_block(self.young_adult_events),
        }
        for k, v in replacements.items():
            template = template.replace(k, v)
        return template

    def save_html(self) -> Path:
        out = OUTPUT_DIR / f"email_{self.today.strftime('%Y_%m_%d')}.html"
        out.write_text(self.build_html())
        return out

    # ---- Plain-text email ----------------------------------------------------

    def build_plain(self) -> str:
        sep = "-" * 60
        sunset_line = (
            f"\nSabbath Begins (Fri): {self.sabbath_times.begins}"
            f"  |  Sabbath Ends (Sat): {self.sabbath_times.ends}"
            if self.sabbath_times else ""
        )
        lines = [
            "MIDDLETOWN PORTLAND SDA CHURCH",
            f"Weekly Communications — {self.today.strftime('%B %-d, %Y')}",
            "",
            f"Next Sabbath: {_format_date(self.sabbath)} ({self.days_until} day(s) away){sunset_line}",
            "",
            sep, "UPCOMING SPEAKERS", sep,
            _speakers_plain(self.speakers),
            sep, "THIS WEEK'S SERVICE", sep,
            _media_plain(self.media),
            sep, "CHURCH EVENTS", sep,
            _event_plain_block(self.general_events),
            sep, "YOUTH & YOUNG ADULTS", sep,
            _event_plain_block(self.youth_events + self.young_adult_events),
            sep, "CAMP WINNEKEAG PATHFINDER LODGE CAMPAIGN", sep,
            "  Help build a dedicated lodge for the entire Southern New England Conference.",
            "  Goal: just under $2 million — break ground this fall.",
            "  Donate:    https://campwngk.maxcheckout.com/",
            "  Learn more: https://mpsdac.org/camp-winnekeag/",
            "",
            sep, "ONLINE GIVING", sep,
            "  Tithes & Offerings (AdventistGiving):",
            "    https://adventistgiving.org/#/org/AN4MGV/envelope/start",
            "  Church Giving Page:",
            "    https://mpsdac.org/giving",
            "",
            sep, "IMPORTANT LINKS", sep,
            "  sneconline.org  |  atlantic-union.org  |  snecyouth.com  |  yasnec.org",
            "",
        ]
        return "\n".join(lines)

    # ---- Open email ----------------------------------------------------------

    def open_mailto(self) -> None:
        body = self.build_plain()
        mailto = (
            f"mailto:{urllib.parse.quote(TO)}"
            f"?subject={urllib.parse.quote(SUBJECT)}"
            f"&body={urllib.parse.quote(body)}"
        )
        webbrowser.open(mailto)

    def open_html_preview(self) -> Path:
        """Save HTML and open it in the browser for review/copy-paste."""
        path = self.save_html()
        webbrowser.open(path.as_uri())
        return path

    # ---- Newsletter ----------------------------------------------------------

    def build_newsletter_html(self) -> str:
        template = (TEMPLATE_DIR / "newsletter_template.html").read_text()
        month_year = self.today.strftime("%B %Y")
        all_events = self.general_events + self.youth_events + self.young_adult_events
        highlights = (
            f"This month we have <strong>{len(all_events)} upcoming events</strong>. "
            "Sabbath services continue every week — see the speaker schedule below."
        )
        replacements = {
            "{{generated_date}}": self.today.strftime("%B %-d, %Y"),
            "{{month_year}}": month_year,
            "{{ministry_highlights}}": highlights,
            "{{speakers_table}}": _speakers_table_html(self.speakers),
            "{{church_events_section}}": _event_html_block(self.general_events),
            "{{conference_events_section}}": "",
            "{{youth_events_section}}": _event_html_block(self.youth_events),
            "{{young_adults_section}}": _event_html_block(self.young_adult_events),
        }
        for k, v in replacements.items():
            template = template.replace(k, v)
        return template

    def build_newsletter_md(self) -> str:
        today_str = self.today.strftime("%B %-d, %Y")
        month_year = self.today.strftime("%B %Y")

        def md_events(events: List[Event]) -> str:
            if not events:
                return "_No upcoming events._\n"
            lines = []
            for e in events:
                lines.append(f"### {e.title}")
                if e.date_str:
                    lines.append(f"**Date:** {e.date_str}")
                if e.location:
                    lines.append(f"**Location:** {e.location}")
                if e.desc_short:
                    lines.append(e.desc_short)
                if e.url:
                    lines.append(f"[More info]({e.url})")
                lines.append("")
            return "\n".join(lines)

        def md_speakers(entries: List[SpeakerEntry]) -> str:
            if not entries:
                return "_Speaker schedule not available._\n"
            lines = ["| Date | Speaker |", "|------|---------|"]
            for s in entries:
                lines.append(f"| {s.date_str} | {s.speaker} |")
            return "\n".join(lines) + "\n"

        return f"""# Middletown Portland SDA Church
## Monthly Newsletter — {month_year}

_Generated: {today_str}_

---

## Upcoming Speakers

{md_speakers(self.speakers)}

---

## Church Events

{md_events(self.general_events)}

---

## Youth & Young Adults

{md_events(self.youth_events + self.young_adult_events)}

---

## Important Links

- [Southern New England Conference](https://www.sneconline.org)
- [Atlantic Union Conference](https://atlantic-union.org)
- [SNEC Youth Ministries](https://snecyouth.com)
- [Young Adults SNEC](https://yasnec.org)
"""


# Monkey-patch Event with a desc_short property
def _desc_short(self) -> str:
    return self.description[:200] + "…" if len(self.description) > 200 else self.description

Event.desc_short = property(_desc_short)
