#!/usr/bin/env python3
"""
Middletown Portland SDA Church — Communications GUI
Run: python3 app.py
Then open http://localhost:5000 in your browser.
"""

import json
import os
import sys
import threading
import time
import webbrowser
from datetime import date
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from scrapers import MPSDACscraper, SpeakerCalendar, YouTubeScraper, get_sabbath_times
from email_generator import EmailGenerator, _next_sabbath

# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_FILE = BASE_DIR / "output" / "gui_state.json"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_THUMB_SIZE = (600, 600)

app = Flask(__name__, template_folder="templates/gui")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {"photo_slots": {}, "custom_text": {}}


def save_state(state: dict) -> None:
    CACHE_FILE.write_text(json.dumps(state, indent=2))


def photo_library() -> list[dict]:
    photos = []
    for f in sorted(UPLOAD_DIR.iterdir()):
        if f.suffix.lower() in ALLOWED_EXT and not f.name.startswith("thumb_"):
            photos.append({
                "name": f.name,
                "url": f"/uploads/{f.name}",
                "thumb": f"/uploads/thumb_{f.name}" if (UPLOAD_DIR / f"thumb_{f.name}").exists() else f"/uploads/{f.name}",
                "size_kb": round(f.stat().st_size / 1024),
            })
    return photos


def make_thumb(src: Path) -> None:
    dest = src.parent / f"thumb_{src.name}"
    if dest.exists():
        return
    try:
        img = Image.open(src)
        img.thumbnail(MAX_THUMB_SIZE, Image.LANCZOS)
        img.save(dest)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Data fetching (cached to module-level dict so page reloads stay fast)
# ---------------------------------------------------------------------------

_data_cache: dict = {}


def fetch_all_data(force: bool = False) -> dict:
    global _data_cache
    if _data_cache and not force:
        return _data_cache

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

    _data_cache = {
        "speakers": [
            {"date": s.date_str, "speaker": s.speaker, "sermon": s.sermon_title}
            for s in speakers
        ],
        "events": [
            {
                "title": e.title,
                "date": e.date_str,
                "parsed_date": e.parsed_date.isoformat() if e.parsed_date else None,
                "day": e.parsed_date.strftime("%-d") if e.parsed_date else "—",
                "month": e.parsed_date.strftime("%b").upper() if e.parsed_date else "",
                "location": e.location,
                "description": e.description[:150] if e.description else "",
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
            "date": _next_sabbath().strftime("%A, %B %-d, %Y"),
            "days": (_next_sabbath() - date.today()).days,
            "begins": sabbath_times.begins if sabbath_times else "",
            "ends": sabbath_times.ends if sabbath_times else "",
        },
        "fetched_at": time.strftime("%I:%M %p"),
    }
    return _data_cache


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    data = fetch_all_data()
    state = load_state()
    photos = photo_library()
    return render_template(
        "index.html",
        data=data,
        state=state,
        photos=photos,
        today=date.today().strftime("%B %-d, %Y"),
    )


@app.route("/portal")
def portal():
    data = fetch_all_data()
    return render_template("portal.html", data=data)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    files = request.files.getlist("photos")
    if not files:
        return jsonify({"error": "No files"}), 400
    saved = []
    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        dest = UPLOAD_DIR / f.filename
        # Avoid overwriting — append counter if needed
        counter = 1
        while dest.exists():
            dest = UPLOAD_DIR / f"{Path(f.filename).stem}_{counter}{ext}"
            counter += 1
        f.save(dest)
        make_thumb(dest)
        saved.append({
            "name": dest.name,
            "url": f"/uploads/{dest.name}",
            "thumb": f"/uploads/thumb_{dest.name}",
        })
    return jsonify({"uploaded": saved})


@app.route("/api/delete-photo", methods=["POST"])
def api_delete_photo():
    name = request.json.get("name", "")
    if not name or "/" in name:
        return jsonify({"error": "Invalid"}), 400
    for prefix in ("", "thumb_"):
        p = UPLOAD_DIR / f"{prefix}{name}"
        if p.exists():
            p.unlink()
    # Remove from any slots
    state = load_state()
    state["photo_slots"] = {k: v for k, v in state["photo_slots"].items() if v != name}
    save_state(state)
    return jsonify({"ok": True})


@app.route("/api/assign-slot", methods=["POST"])
def api_assign_slot():
    slot = request.json.get("slot", "")
    photo = request.json.get("photo", "")  # empty string = clear slot
    state = load_state()
    if photo:
        state["photo_slots"][slot] = photo
    else:
        state["photo_slots"].pop(slot, None)
    save_state(state)
    return jsonify({"ok": True, "slots": state["photo_slots"]})


@app.route("/api/save-text", methods=["POST"])
def api_save_text():
    key = request.json.get("key", "")
    value = request.json.get("value", "")
    state = load_state()
    state.setdefault("custom_text", {})[key] = value
    save_state(state)
    return jsonify({"ok": True})


@app.route("/api/refresh-data", methods=["POST"])
def api_refresh_data():
    global _data_cache
    _data_cache = {}
    data = fetch_all_data(force=True)
    return jsonify(data)


@app.route("/preview/email")
def preview_email():
    data = fetch_all_data()
    state = load_state()
    gen = _build_generator(data, state)
    return gen.build_html()


@app.route("/preview/newsletter")
def preview_newsletter():
    data = fetch_all_data()
    state = load_state()
    html = _build_newsletter_html(data, state)
    return html


@app.route("/generate/email")
def generate_email():
    data = fetch_all_data()
    state = load_state()
    gen = _build_generator(data, state)
    path = gen.save_html()
    return send_file(path, as_attachment=True, download_name=path.name)


@app.route("/generate/newsletter")
def generate_newsletter():
    data = fetch_all_data()
    state = load_state()
    html = _build_newsletter_html(data, state)
    out = OUTPUT_DIR / f"newsletter_{date.today().strftime('%Y_%m')}.html"
    out.write_text(html)
    return send_file(out, as_attachment=True, download_name=out.name)


@app.route("/generate/newsletter-md")
def generate_newsletter_md():
    data = fetch_all_data()
    state = load_state()
    gen = _build_generator(data, state)
    md = gen.build_newsletter_md()
    out = OUTPUT_DIR / f"newsletter_{date.today().strftime('%Y_%m')}.md"
    out.write_text(md)
    return send_file(out, as_attachment=True, download_name=out.name)


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def _build_generator(data: dict, state: dict) -> EmailGenerator:
    from scrapers.base import Event
    from scrapers.calendar import SpeakerEntry
    from scrapers.youtube import MediaBundle, YouTubeVideo
    from scrapers.sunset import SabbathTimes

    speakers = [
        SpeakerEntry(date_str=s["date"], speaker=s["speaker"], sermon_title=s["sermon"])
        for s in data.get("speakers", [])
    ]

    events = []
    for ev in data.get("events", []):
        e = Event(
            title=ev["title"],
            date_str=ev["date"],
            source="MPSDAC",
            description=ev["description"],
            location=ev["location"],
            url=ev["url"],
            category=ev["category"],
        )
        if ev.get("parsed_date"):
            try:
                from datetime import date as _date
                e.parsed_date = _date.fromisoformat(ev["parsed_date"])
            except Exception:
                pass
        events.append(e)

    media = None
    md = data.get("media", {})
    if md:
        stream = (
            YouTubeVideo(
                video_id=md["stream"]["url"].split("/")[-1],
                title=md["stream"]["title"],
                url=md["stream"]["url"],
            ) if md.get("stream") else None
        )
        video = (
            YouTubeVideo(
                video_id=md["video"]["url"].split("/")[-1],
                title=md["video"]["title"],
                url=md["video"]["url"],
            ) if md.get("video") else None
        )
        media = MediaBundle(latest_stream=stream, latest_video=video)

    sb = data.get("sabbath", {})
    sabbath_times = (
        SabbathTimes(
            friday_date=date.today(),
            saturday_date=date.today(),
            begins=sb.get("begins", ""),
            ends=sb.get("ends", ""),
        ) if sb.get("begins") else None
    )

    return EmailGenerator(
        speakers=speakers,
        events=events,
        media=media,
        sabbath_times=sabbath_times,
    )


def _build_newsletter_html(data: dict, state: dict) -> str:
    gen = _build_generator(data, state)
    base_html = gen.build_newsletter_html()

    # Inject custom photos into the newsletter
    slots = state.get("photo_slots", {})
    custom_text = state.get("custom_text", {})

    hero_img = slots.get("hero")
    if hero_img:
        hero_url = f"http://localhost:5050/uploads/{hero_img}"
        base_html = base_html.replace(
            "{{hero_image}}",
            f'<img src="{hero_url}" style="width:100%;max-height:280px;object-fit:cover;border-radius:8px;margin-bottom:20px" alt="Hero photo">',
        )
    else:
        base_html = base_html.replace("{{hero_image}}", "")

    for i in range(1, 4):
        slot_key = f"section_{i}_image"
        img = slots.get(slot_key)
        if img:
            img_url = f"http://localhost:5050/uploads/{img}"
            base_html = base_html.replace(
                f"{{{{{slot_key}}}}}",
                f'<img src="{img_url}" style="width:100%;max-height:220px;object-fit:cover;border-radius:6px;margin:12px 0" alt="">',
            )
        else:
            base_html = base_html.replace(f"{{{{{slot_key}}}}}", "")

    highlight = custom_text.get("highlight", "")
    if highlight:
        base_html = base_html.replace("{{ministry_highlights}}", highlight)

    return base_html


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

PORT = 5050


def open_browser():
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    print("\n  Middletown Portland SDA Church — Communications GUI")
    print(f"  Opening at http://localhost:{PORT}\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=PORT)
