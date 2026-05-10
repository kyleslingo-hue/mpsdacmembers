# Church Communications Script
## Middletown Portland SDA Church

Automates weekly collection of SDA event information and generates pre-filled
email drafts for church communications.

---

## Quick Start

```bash
cd church-comms
pip3 install -r requirements.txt
python3 church_comms.py
```

---

## Usage

| Command | What it does |
|---|---|
| `python3 church_comms.py` | Scrape events + open email draft in mail client |
| `python3 church_comms.py --newsletter` | Generate monthly newsletter (HTML + Markdown) |
| `python3 church_comms.py --email-only` | Build email, save to file, skip opening mail client |
| `python3 church_comms.py --save-html` | Also save email HTML to `output/` |
| `python3 church_comms.py --no-cache` | Force re-scrape (ignore 6-hour cache) |
| `python3 church_comms.py --debug` | Verbose logging to stderr + log file |

---

## Speaker Calendar (SharePoint)

The script attempts to download the speaker calendar from the SharePoint link
directly. This works **only if the file is shared as "Anyone with the link can
view"**.

If the download fails (e.g., requires login), export the file manually:

1. Open the SharePoint link in your browser
2. File → Download as Excel (.xlsx)
3. Save as `speaker_calendar.xlsx` in this folder
4. Run the script — it will pick it up automatically

---

## Event Sources

| Source | URL | Category |
|---|---|---|
| SNEC | sneconline.org | Conference |
| Atlantic Union | atlantic-union.org | Conference |
| SNEC Youth | snecyouth.com | Youth |
| YASNEC | yasnec.org | Young Adults |

---

## Output Files

All outputs land in `output/`:

| File | Description |
|---|---|
| `event_cache.json` | Cached event data (refreshes every 6 hours) |
| `email_YYYY_MM_DD.html` | Saved email HTML (`--save-html`) |
| `email_YYYY_MM_DD.txt` | Plain-text email (`--email-only`) |
| `newsletter_YYYY_MM.html` | Monthly newsletter HTML (`--newsletter`) |
| `newsletter_YYYY_MM.md` | Monthly newsletter Markdown (`--newsletter`) |
| `newsletter_YYYY_MM.pdf` | PDF newsletter — requires `pip3 install weasyprint` |
| `logs/run_*.log` | Run logs |

---

## Notes

- Duplicate events are detected by hashing title + date — same event won't appear twice
- Only future events are included
- Cache TTL is 6 hours — run with `--no-cache` to force refresh
- PDF export requires `weasyprint`: `pip3 install weasyprint`
