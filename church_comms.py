#!/usr/bin/env python3
"""
Middletown Portland SDA Church — Communications Automation Script

Usage:
  python church_comms.py                  Weekly email draft (opens mail client)
  python church_comms.py --newsletter     Generate monthly newsletter files
  python church_comms.py --email-only     Build email, skip browser open
  python church_comms.py --save-html      Save generated email HTML to output/
  python church_comms.py --debug          Verbose logging
  python church_comms.py --no-cache       Ignore cached events
"""

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Bootstrap path so sub-modules resolve from this file's directory
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from scrapers import MPSDACscraper, SpeakerCalendar, YouTubeScraper, MediaBundle, get_sabbath_times
from scrapers.base import Event
from scrapers.calendar import SpeakerEntry
from email_generator import EmailGenerator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = OUTPUT_DIR / "logs"
CACHE_FILE = OUTPUT_DIR / "event_cache.json"
CACHE_TTL_HOURS = 6

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

console = Console()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(debug: bool) -> None:
    log_file = LOGS_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stderr) if debug else logging.NullHandler(),
        ],
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _events_to_dict(events: List[Event]) -> list:
    return [
        {
            "title": e.title,
            "date_str": e.date_str,
            "source": e.source,
            "description": e.description,
            "location": e.location,
            "url": e.url,
            "category": e.category,
            "parsed_date": e.parsed_date.isoformat() if e.parsed_date else None,
        }
        for e in events
    ]


def _dict_to_events(data: list) -> List[Event]:
    events = []
    for d in data:
        e = Event(
            title=d["title"],
            date_str=d["date_str"],
            source=d["source"],
            description=d.get("description", ""),
            location=d.get("location", ""),
            url=d.get("url", ""),
            category=d.get("category", "General"),
        )
        if d.get("parsed_date"):
            try:
                e.parsed_date = date.fromisoformat(d["parsed_date"])
            except Exception:
                pass
        events.append(e)
    return events


def load_cache() -> tuple:
    """Returns (events, speakers_raw, cache_valid)."""
    if not CACHE_FILE.exists():
        return [], [], False
    try:
        data = json.loads(CACHE_FILE.read_text())
        saved_at = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
        age_hours = (datetime.now() - saved_at).total_seconds() / 3600
        if age_hours > CACHE_TTL_HOURS:
            return [], [], False
        events = _dict_to_events(data.get("events", []))
        speakers_raw = data.get("speakers", [])
        return events, speakers_raw, True
    except Exception:
        return [], [], False


def save_cache(events: List[Event], speakers: List[SpeakerEntry]) -> None:
    speakers_raw = [
        {
            "date_str": s.date_str,
            "speaker": s.speaker,
            "sermon_title": s.sermon_title,
            "notes": s.notes,
            "parsed_date": s.parsed_date.isoformat() if s.parsed_date else None,
        }
        for s in speakers
    ]
    payload = {
        "saved_at": datetime.now().isoformat(),
        "events": _events_to_dict(events),
        "speakers": speakers_raw,
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2))


def speakers_from_raw(raw: list) -> List[SpeakerEntry]:
    entries = []
    for d in raw:
        s = SpeakerEntry(
            date_str=d["date_str"],
            speaker=d["speaker"],
            sermon_title=d.get("sermon_title", ""),
            notes=d.get("notes", ""),
        )
        if d.get("parsed_date"):
            try:
                s.parsed_date = date.fromisoformat(d["parsed_date"])
            except Exception:
                pass
        entries.append(s)
    return entries


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def deduplicate(events: List[Event]) -> List[Event]:
    seen = set()
    unique = []
    for e in events:
        if e.uid not in seen:
            seen.add(e.uid)
            unique.append(e)
    return unique


def sort_events(events: List[Event]) -> List[Event]:
    def key(e: Event):
        return e.parsed_date or date(2099, 12, 31)
    return sorted(events, key=key)


# ---------------------------------------------------------------------------
# Rich display helpers
# ---------------------------------------------------------------------------

def print_header() -> None:
    console.print(
        Panel.fit(
            "[bold white]Middletown Portland SDA Church[/bold white]\n"
            "[dim]Communications Automation Script[/dim]",
            border_style="blue",
            padding=(0, 2),
        )
    )
    console.print()


def print_event_table(events: List[Event], title: str) -> None:
    if not events:
        console.print(f"  [dim]No events found for: {title}[/dim]")
        return
    table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=False, expand=False)
    table.add_column("Date", style="cyan", no_wrap=True, min_width=12)
    table.add_column("Title", style="white", max_width=50)
    table.add_column("Source", style="dim", min_width=14)
    table.add_column("Location", style="dim", max_width=22)
    for e in events:
        table.add_row(e.date_str[:20], e.title[:50], e.source, e.location[:22])
    console.print(table)


def print_speakers(entries: List[SpeakerEntry]) -> None:
    if not entries:
        console.print("  [dim]Speaker schedule not available.[/dim]")
        return
    table = Table(title="Upcoming Speakers", box=box.SIMPLE_HEAVY)
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Speaker", style="bold white")
    table.add_column("Sermon Title", style="italic")
    table.add_column("Notes", style="dim")
    for s in entries[:10]:
        table.add_row(s.date_str[:20], s.speaker, s.sermon_title, s.notes)
    console.print(table)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_data(use_cache: bool = True):
    if use_cache:
        events, speakers_raw, valid = load_cache()
        if valid:
            console.print("[green]✓[/green] Using cached data (< 6h old). Pass [bold]--no-cache[/bold] to refresh.\n")
            speakers = speakers_from_raw(speakers_raw)
            media = YouTubeScraper().fetch_media()
            return events, speakers, media

    all_events: List[Event] = []
    speakers: List[SpeakerEntry] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=False,
    ) as progress:

        # Speaker calendar
        task = progress.add_task("[cyan]Fetching speaker calendar…", total=None)
        try:
            cal = SpeakerCalendar()
            speakers = cal.fetch()
            progress.update(
                task,
                description=f"[green]✓[/green] Speaker calendar — {len(speakers)} upcoming entries",
                completed=True,
            )
        except Exception as e:
            progress.update(task, description=f"[yellow]⚠[/yellow] Speaker calendar — {e}")
        time.sleep(0.2)

        # Church events
        task = progress.add_task("[cyan]Fetching church events (mpsdac.org)…", total=None)
        try:
            found = MPSDACscraper().scrape()
            all_events.extend(found)
            progress.update(
                task,
                description=f"[green]✓[/green] Church events — {len(found)} events",
                completed=True,
            )
        except Exception as e:
            progress.update(
                task,
                description=f"[yellow]⚠[/yellow] Church events — {e}",
                completed=True,
            )

        # YouTube — latest video + live stream
        media = None
        task = progress.add_task("[cyan]Fetching YouTube media…", total=None)
        try:
            media = YouTubeScraper().fetch_media()
            parts = []
            if media.latest_stream:
                parts.append(f"stream: {media.latest_stream.title[:40]}")
            if media.latest_video:
                parts.append(f"video: {media.latest_video.title[:40]}")
            progress.update(
                task,
                description=f"[green]✓[/green] YouTube — {' | '.join(parts) or 'none found'}",
                completed=True,
            )
        except Exception as e:
            progress.update(
                task,
                description=f"[yellow]⚠[/yellow] YouTube — {e}",
                completed=True,
            )

    all_events = deduplicate(all_events)
    all_events = sort_events(all_events)

    save_cache(all_events, speakers)
    return all_events, speakers, media


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Middletown Portland SDA Church — Communications Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--newsletter", action="store_true", help="Generate monthly newsletter")
    parser.add_argument("--email-only", action="store_true", help="Generate email body, don't open mail client")
    parser.add_argument("--save-html", action="store_true", help="Save email HTML to output/")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached data and re-scrape")
    args = parser.parse_args()

    setup_logging(args.debug)
    print_header()

    # ---- Collect data -------------------------------------------------------
    console.rule("[bold blue]Collecting Data")
    events, speakers, media = collect_data(use_cache=not args.no_cache)

    # ---- Summary ------------------------------------------------------------
    console.print()
    console.rule("[bold blue]Summary")

    conf_events = [e for e in events if e.category == "Conference"]
    youth_events = [e for e in events if e.category == "Youth"]
    ya_events = [e for e in events if e.category == "Young Adults"]
    gen_events = [e for e in events if e.category not in ("Conference", "Youth", "Young Adults")]

    console.print(f"  [bold]Total upcoming events:[/bold] {len(events)}")
    console.print(f"    Conference:    {len(conf_events)}")
    console.print(f"    Youth:         {len(youth_events)}")
    console.print(f"    Young Adults:  {len(ya_events)}")
    console.print(f"    General:       {len(gen_events)}")
    console.print(f"  [bold]Speaker entries:[/bold] {len(speakers)}")
    console.print()

    print_speakers(speakers)
    console.print()
    print_event_table(events[:20], "All Upcoming Events (top 20)")
    console.print()

    # ---- Generate outputs ---------------------------------------------------
    if media:
        if media.latest_stream:
            console.print(f"  [bold]Live stream:[/bold] {media.latest_stream.title[:60]}")
            console.print(f"    {media.latest_stream.url}")
        if media.latest_video:
            console.print(f"  [bold]Latest upload:[/bold] {media.latest_video.title[:60]}")
            console.print(f"    {media.latest_video.url}")
        console.print()

    from email_generator import _next_sabbath
    sabbath_times = get_sabbath_times(_next_sabbath())

    gen = EmailGenerator(speakers=speakers, events=events, media=media, sabbath_times=sabbath_times)

    if args.newsletter:
        console.rule("[bold blue]Generating Newsletter")
        html_out = OUTPUT_DIR / f"newsletter_{date.today().strftime('%Y_%m')}.html"
        md_out = OUTPUT_DIR / f"newsletter_{date.today().strftime('%Y_%m')}.md"

        html_out.write_text(gen.build_newsletter_html())
        md_out.write_text(gen.build_newsletter_md())

        console.print(f"  [green]✓[/green] HTML newsletter → [bold]{html_out.relative_to(BASE_DIR)}[/bold]")
        console.print(f"  [green]✓[/green] Markdown newsletter → [bold]{md_out.relative_to(BASE_DIR)}[/bold]")

        # Optional PDF via weasyprint
        try:
            from weasyprint import HTML as WPHTML
            pdf_out = OUTPUT_DIR / f"newsletter_{date.today().strftime('%Y_%m')}.pdf"
            WPHTML(string=gen.build_newsletter_html()).write_pdf(str(pdf_out))
            console.print(f"  [green]✓[/green] PDF newsletter → [bold]{pdf_out.relative_to(BASE_DIR)}[/bold]")
        except ImportError:
            console.print("  [dim]PDF skipped — install weasyprint to enable PDF export.[/dim]")

    console.rule("[bold blue]Generating Email")

    # Always save + open HTML preview in browser
    try:
        html_path = gen.open_html_preview()
        console.print(f"  [green]✓[/green] HTML email → [bold]{html_path.relative_to(BASE_DIR)}[/bold]")
        console.print("  [cyan]Opened in browser for review.[/cyan]")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Could not open browser: {e}")

    if not args.email_only:
        console.print()
        console.print("  [cyan]Opening mail client with plain-text draft…[/cyan]")
        try:
            gen.open_mailto()
            console.print("  [green]✓[/green] Mail client opened.")
        except Exception as e:
            console.print(f"  [yellow]⚠[/yellow] Could not open mail client: {e}")
    else:
        plain_out = OUTPUT_DIR / f"email_{date.today().strftime('%Y_%m_%d')}.txt"
        plain_out.write_text(gen.build_plain())
        console.print(f"  [green]✓[/green] Plain-text draft → [bold]{plain_out.relative_to(BASE_DIR)}[/bold]")

    console.print()
    console.print(Panel.fit("[bold green]Done![/bold green]", border_style="green"))


if __name__ == "__main__":
    main()
