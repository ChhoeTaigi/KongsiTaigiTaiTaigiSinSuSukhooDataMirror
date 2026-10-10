"""Parse the crawled 台語新詞辭庫 pages into CSV and JSON.

Each list page (https://www.taigitv.org.tw/taigi-words?page=N) holds up to
12 entry cards; the entry detail page (/taigi-words/{id}) repeats the card and
may add 例句 (example sentences) and 相關影音 (YouTube videos). A card contains:

- 漢字 (headword; the site calls it 詞目) and the entry id (from the /taigi-words/{id} link)
- one or more 音讀 (KPL readings), each with its own audio URL (WAV); POJ is
  derived from KPL with lomaji.kpl_to_poj
- 對應華語 (Mandarin gloss)
- zero or more 標籤 (tag names)

A detail page may add:

- 例句: rows labelled 漢羅例句 / 台羅例句 / 對應華語 (POJ is derived from 台羅)
- 相關影音: <iframe> YouTube embeds, normalised to watch URLs

The site lists entries newest first; the output is sorted by id ascending so
that diffs between versions stay stable.
"""

import csv
import html
import json
import os
import re
import sys
from pathlib import Path

try:
    from lomaji import kpl_to_poj
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from lomaji import kpl_to_poj

SITE = "https://www.taigitv.org.tw"
MIRROR_BASE = "https://chhoetaigi.github.io/KongsiTaigiTaiTaigiSinSuSukhooDataMirror/public"

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

CSV_FIELDS = [
    "id", "漢字", "KPL", "POJ", "對應華語", "標籤",
    "例句漢羅", "例句KPL", "例句POJ", "例句華語", "相關影音",
    "音檔", "音檔來源網址", "音檔原始網址", "網址",
]
# Separators used inside a CSV cell when an entry has several readings / tags.
MULTI_SEP = "/"       # KPL, POJ, 標籤, 音檔
URL_SEP = ";"         # 相關影音, 音檔來源網址, 音檔原始網址 (URLs contain "/")
SENTENCE_SEP = "\n"   # 例句* (sentences may contain "/" and ";")

_CARD_SPLIT = re.compile(r'<div class="col-lg-4 mb-20">')
_ID = re.compile(r'/taigi-words/(\d+)"')
_TITLE = re.compile(r'<div class="h3">\s*<a [^>]*>(.*?)</a>', re.S)
_READING_BLOCK = re.compile(r'音讀：</div>\s*<div class="col-8 pl-0">(.*?)</div>\s*</div>', re.S)
_READING_P = re.compile(r'<p class="eng[^"]*">(.*?)</p>', re.S)
_SPAN = re.compile(r'<span[^>]*>(.*?)</span>', re.S)
_VOICE = re.compile(r'data-content="([^"]*)"')
_HUAGI_BLOCK = re.compile(r'對應華語：</div>\s*<div class="col-8 pl-0">(.*?)</div>\s*</div>', re.S)
_TAG = re.compile(r'/taigi-words/tag/(\d+)"\s*title="#?([^"]*)"')
_SECTION = re.compile(r'<div class="pop-sec">(.*?)(?=<div class="pop-sec">|$)', re.S)
_SAMPLE_ROW = re.compile(
    r'<div class="taigi-words-sample"><span>(.*?)</span></div>\s*</div>\s*<div class="col">(.*?)</div>', re.S
)
_IFRAME_SRC = re.compile(r'<iframe[^>]*\ssrc=["\']([^"\']+)["\']', re.S)
_YOUTUBE = re.compile(
    r'^(?:https?:)?//(?:www\.|m\.)?(?:youtube\.com|youtube-nocookie\.com|youtu\.be)'
    r'/(?:embed/|live/|shorts/|watch\?v=)?([A-Za-z0-9_-]{6,})(?:[?&](.*))?$'
)
_BARE_URL = re.compile(r'https?://[^\s<>"\']+')
_SAMPLE_LABELS = {"漢羅例句": "漢羅", "台羅例句": "KPL", "對應華語": "華語"}


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(html.unescape(text).split())


def _clean_multiline(text):
    """Flatten a sentence cell: <br> becomes a space so one sentence stays on one line."""
    text = re.sub(r"<br\s*/?>", " ", text)
    return _clean(text)


def normalize_video_url(src):
    """YouTube embed/live/short/watch URL → canonical watch URL (keeping a start offset);
    anything else → absolute URL as given."""
    src = html.unescape(src).strip().rstrip(".,;")
    m = _YOUTUBE.match(src)
    if not m:
        return "https:" + src if src.startswith("//") else src
    video_id, query = m.group(1), m.group(2) or ""
    url = f"https://www.youtube.com/watch?v={video_id}"
    for part in query.split("&"):
        if part.startswith(("start=", "t=")):
            seconds = part.split("=", 1)[1].rstrip("s")
            if seconds.isdigit() and int(seconds) > 0:
                url += f"&t={seconds}s"
            break
    return url


def parse_detail(page_html):
    """Return {"例句": [...], "相關影音": [...]} from an entry detail page."""
    start = page_html.find("<main")
    end = page_html.find("</main>")
    main = page_html[start:end] if start >= 0 else page_html
    sentences, videos = [], []
    for section in _SECTION.findall(main):
        rows = _SAMPLE_ROW.findall(section)
        if rows:
            group = {"漢羅": "", "KPL": "", "POJ": "", "華語": ""}
            for label, value in rows:
                key = _SAMPLE_LABELS.get(_clean(label))
                if key:
                    group[key] = _clean_multiline(value)
            group["POJ"] = kpl_to_poj(group["KPL"])
            sentences.append(group)
        if "相關影音" in section:
            # Usually <iframe> embeds; a few entries paste a bare URL as text instead.
            srcs = _IFRAME_SRC.findall(section) + _BARE_URL.findall(re.sub(r"<[^>]+>", " ", section))
            for src in srcs:
                url = normalize_video_url(src)
                if url not in videos:
                    videos.append(url)
    return {"例句": sentences, "相關影音": videos}


def _audio_name(entry_id, index, source_url):
    """Local audio filename: {id}.wav for the first reading, {id}-{n}.wav after.

    The extension follows the source file (almost always .wav, one .mp3).
    """
    ext = os.path.splitext(source_url.split("?")[0])[1].lower() or ".wav"
    stem = str(entry_id) if index == 1 else f"{entry_id}-{index}"
    return stem + ext


def parse_page(page_html):
    """Return the list of entry dicts found in one list page."""
    start = page_html.find('class="s4-btng"')
    end = page_html.find('class="pag-nav"')
    if start < 0:
        return []
    body = page_html[start:end] if end > start else page_html[start:]

    entries = []
    for card in _CARD_SPLIT.split(body)[1:]:
        m_id = _ID.search(card)
        m_title = _TITLE.search(card)
        if not (m_id and m_title):
            continue
        entry_id = int(m_id.group(1))

        readings = []
        m_block = _READING_BLOCK.search(card)
        if m_block:
            block = m_block.group(1)
            paragraphs = _READING_P.findall(block) or [block]
            for i, p in enumerate(paragraphs, start=1):
                m_span = _SPAN.search(p)
                m_voice = _VOICE.search(p)
                voice_url = html.unescape(m_voice.group(1)).strip() if m_voice else ""
                kpl = _clean(m_span.group(1)) if m_span else _clean(p)
                reading = {
                    "KPL": kpl,
                    "POJ": kpl_to_poj(kpl),
                    "音檔": _audio_name(entry_id, i, voice_url) if voice_url else "",
                    "音檔來源網址": "",   # mirror URL, filled by apply_mirror_urls once the version is known
                    "音檔原始網址": voice_url,
                }
                if reading["KPL"] or reading["音檔原始網址"]:
                    readings.append(reading)

        m_huagi = _HUAGI_BLOCK.search(card)
        huagi = _clean(m_huagi.group(1)) if m_huagi else ""

        tags = []
        for tag_id, name in _TAG.findall(card):
            name = _clean(name)
            if name not in tags:
                tags.append(name)

        entries.append({
            "id": entry_id,
            "漢字": _clean(m_title.group(1)),
            "音讀": readings,
            "對應華語": huagi,
            "標籤": tags,
            "例句": [],
            "相關影音": [],
            "網址": f"{SITE}/taigi-words/{entry_id}",
        })
    return entries


def attach_details(entries, detail_dir):
    """Merge parse_detail() of detail_dir/{id}.html into each entry (missing files are skipped)."""
    detail_dir = Path(detail_dir)
    found = 0
    for e in entries:
        path = detail_dir / f"{e['id']}.html"
        if not path.exists():
            continue
        found += 1
        e.update(parse_detail(path.read_text(encoding="utf-8")))
    return found


def _page_number(path):
    m = re.search(r"(\d+)", Path(path).stem)
    return int(m.group(1)) if m else 0


def parse_pages_dir(pages_dir, detail_dir=None):
    """Parse every page_*.html in pages_dir (and detail_dir/{id}.html); return entries sorted by id."""
    pages = sorted(Path(pages_dir).glob("page_*.html"), key=_page_number)
    if not pages:
        raise FileNotFoundError(f"No page_*.html found in {pages_dir}")
    by_id = {}
    for page in pages:
        for entry in parse_page(page.read_text(encoding="utf-8")):
            by_id.setdefault(entry["id"], entry)
    entries = [by_id[k] for k in sorted(by_id)]
    if detail_dir is not None:
        found = attach_details(entries, detail_dir)
        print(f"Detail pages found for {found} of {len(entries)} entries")
    return entries


def entry_to_row(entry):
    readings = entry["音讀"]
    tags = entry["標籤"]
    return {
        "id": entry["id"],
        "漢字": entry["漢字"],
        "KPL": MULTI_SEP.join(r["KPL"] for r in readings),
        "POJ": MULTI_SEP.join(r["POJ"] for r in readings),
        "對應華語": entry["對應華語"],
        "標籤": MULTI_SEP.join(tags),
        "例句漢羅": SENTENCE_SEP.join(s["漢羅"] for s in entry.get("例句", [])),
        "例句KPL": SENTENCE_SEP.join(s["KPL"] for s in entry.get("例句", [])),
        "例句POJ": SENTENCE_SEP.join(s["POJ"] for s in entry.get("例句", [])),
        "例句華語": SENTENCE_SEP.join(s["華語"] for s in entry.get("例句", [])),
        "相關影音": URL_SEP.join(entry.get("相關影音", [])),
        "音檔": MULTI_SEP.join(r["音檔"] for r in readings),
        "音檔來源網址": URL_SEP.join(r["音檔來源網址"] for r in readings),
        "音檔原始網址": URL_SEP.join(r["音檔原始網址"] for r in readings),
        "網址": entry["網址"],
    }


def mirror_url(version_name, audio_name):
    return f"{MIRROR_BASE}/{version_name}/imtong/{audio_name}" if audio_name else ""


def apply_mirror_urls(entries, version_name):
    """Point 音檔來源網址 at the GitHub Pages copy of each reading's audio file."""
    for e in entries:
        for r in e["音讀"]:
            r["音檔來源網址"] = mirror_url(version_name, r["音檔"])
    return entries


def apply_missing_audio(entries, missing):
    """Blank 音檔 and 音檔來源網址 for readings whose audio could not be mirrored (keeps 音檔原始網址)."""
    missing = set(missing or ())
    for e in entries:
        for r in e["音讀"]:
            if r["音檔"] in missing:
                r["音檔"] = ""
                r["音檔來源網址"] = ""
    return entries


def write_outputs(entries, csv_output, json_output):
    os.makedirs(os.path.dirname(os.path.abspath(csv_output)), exist_ok=True)
    with open(csv_output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for e in entries:
            w.writerow(entry_to_row(e))
    print(f"Wrote {csv_output}")

    os.makedirs(os.path.dirname(os.path.abspath(json_output)), exist_ok=True)
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {json_output}")


def convert_KongsiTaigiTaiTaigiSinSuSukhooData(pages_dir, csv_output, json_output, detail_dir=None):
    print(f"Parsing pages in {pages_dir}...")
    entries = parse_pages_dir(pages_dir, detail_dir)
    n_readings = sum(len(e["音讀"]) for e in entries)
    print(f"Parsed {len(entries)} entries, {n_readings} readings")
    write_outputs(entries, csv_output, json_output)
    return entries


def _load_manifest():
    manifest = PUBLIC_DIR / "manifest.json"
    if manifest.exists():
        with open(manifest, encoding="utf-8") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) in (3, 4):
        convert_KongsiTaigiTaiTaigiSinSuSukhooData(*args)
    else:
        manifest = _load_manifest()
        latest = manifest.get("latest_version_dir")
        if not latest:
            print("Usage: convert_KongsiTaigiTaiTaigiSinSuSukhooData.py PAGES_DIR CSV_OUT JSON_OUT")
            sys.exit(1)
        version_dir = PUBLIC_DIR / latest
        bunji = version_dir / "bunji"
        entries = parse_pages_dir(str(version_dir / "tangloo" / "pages"), str(version_dir / "tangloo" / "detail"))
        apply_mirror_urls(entries, latest)
        apply_missing_audio(entries, manifest.get("imtong_missing"))
        print(f"Parsed {len(entries)} entries")
        write_outputs(
            entries,
            str(bunji / "KongsiTaigiTaiTaigiSinSuSukhooData.csv"),
            str(bunji / "KongsiTaigiTaiTaigiSinSuSukhooData.json"),
        )
