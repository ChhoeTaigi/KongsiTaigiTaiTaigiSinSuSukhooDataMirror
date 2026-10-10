# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Data mirror for the 公視台語台 台語新詞辭庫 (PTS Taigi neologism lexicon, https://www.taigitv.org.tw/taigi-words). Part of the ChhoeTaigi project. The source offers no bulk download, so the repo crawls the paginated list pages and every entry's detail page, parses them into CSV/JSON, mirrors the pronunciation audio, and hosts everything via GitHub Pages.

Text content is licensed CC BY 4.0 by the source site. The audio licence is not stated separately.

## Commands

```bash
# Activate the Python 3.12 venv
source .venv/bin/activate

# Run the full update pipeline (crawls 180 list pages + ~2,160 detail pages from taigitv.org.tw, detects changes via a SHA256 of the parsed data, converts to CSV/JSON, mirrors audio, writes VERSION_DIFF.md). Takes ~20 min at the default delay.
cd script && python update_data.py

# Same, but skip the audio step / change the request pause
cd script && python update_data.py --no-imtong --delay 0.5

# Re-run only the HTML → CSV/JSON conversion for the latest version (needs tangloo/pages and tangloo/detail, which are gitignored)
cd script && python convert_KongsiTaigiTaiTaigiSinSuSukhooData.py

# Run the KPL → POJ converter tests
cd script && python -m unittest test_lomaji
```

Dependencies: `requests`. Install with `pip install requests`.

## Architecture

### Data Pipeline (`script/`)

1. **`update_data.py`** — Main entry point. Reads the page count from the pagination of `?page=1`, crawls every list page and then every entry detail page into a temp dir, parses them, and hashes the canonical JSON of the parsed entries (the raw HTML cannot be hashed because it embeds a per-request CSRF token). On change it creates a timestamped version directory, keeps the raw pages under `tangloo/pages/` and `tangloo/detail/`, writes `bunji/`, then syncs `imtong/` (audio whose source URL is unchanged is copied from the previous version instead of re-downloaded) and writes `VERSION_DIFF.md`.

2. **`convert_KongsiTaigiTaiTaigiSinSuSukhooData.py`** — Regex-based parsers for the list-page cards (`parse_page`: 漢字, readings, 對應華語, 標籤) and the detail pages (`parse_detail`: 例句 rows and 相關影音 iframes), plus CSV/JSON writers. The detail page repeats the card and may add 例句 / 相關影音, so both are needed. Output is sorted by `id`. Run standalone it re-derives `bunji/` for the latest version and re-applies `imtong_missing` from the manifest.

3. **`lomaji.py`** — KPL Unicode → POJ Unicode, a Python port of KonvertToPOJ's direct route (strip tone → map letters → POJ §21 tone placement, gated by a KPL syllable-shape check). `test_lomaji.py` holds the library's test cases plus entries from this lexicon.

4. **`diff_versions.py`** — Compares two versions of the JSON keyed by `id`; produces `VERSION_DIFF.md`.

### Data Layout (`public/`)

```
public/
  manifest.json              # Latest version dir, entry count, SHA256 of the parsed data
  {YYYYMMDD-HHMM}/           # Timestamped version directory
    bunji/                    # KongsiTaigiTaiTaigiSinSuSukhooData.csv / .json
    imtong/                   # Audio, one file per reading: {id}.wav, {id}-2.wav, ...
    tangloo/pages/            # Raw list pages (page_N.html) — gitignored
    tangloo/detail/           # Raw detail pages ({id}.html) — gitignored
```

### Hosting

- `index.md` is the GitHub Pages landing page
- `.nojekyll` disables Jekyll processing
- Audio files are served directly from `public/{version}/imtong/`

## Important Rules

- **`README.md` and `index.md` must stay in sync.** They have identical content. When updating version references or any other content in one, always update the other to match.
- Be polite to the source server: keep the per-request delay, keep the identifying User-Agent, and never parallelise the crawl.

## Data Notes

- An entry has one `漢字` (the site's 詞目), one `對應華語`, 1–4 readings in `音讀` (each `{KPL, POJ, 音檔, 音檔來源網址, 音檔原始網址}`), 0–4 `標籤` (names only; the user asked to drop tag ids), 0–1 `例句` (`{漢羅, KPL, POJ, 華語}`) and 0–2 `相關影音` (YouTube watch URLs, normalised from the embed src or a pasted bare URL).
- `音檔來源網址` is the GitHub Pages URL of the mirrored file (user's choice); `音檔原始網址` is the upstream URL and is what the audio sync downloads and compares. Both are derived after hashing (`apply_mirror_urls`, `apply_missing_audio`), so the data hash covers only what was parsed.
- CSV multi-value separator is `/` (`KPL`, `POJ`, `標籤`, `音檔`), `;` for URL columns (`相關影音`, `音檔來源網址`, `音檔原始網址`) and a newline for `例句*`. The user asked for `/` between alternative readings explicitly; keep it.
- `POJ` is derived, never scraped. If the converter changes, re-run the standalone convert for the latest version and refresh the manifest hash (the hash covers the parsed entries including `POJ`).
- Local audio names are derived from the entry id, not from the upstream filenames (which mix numeric, Hanji and random-hash names, and one `.mp3`).
- Readings use KPL with Unicode diacritics; normalize to NFC when comparing.

## Terminology (Taigi)

- **bunji** (文字) — text data
- **imtong** (音通) — audio
- **tangloo** (檔路) — file storage / archives
- **sin-sû** (新詞) — neologism
- **sû-khò͘** (辭庫) — lexicon
- **Kong-sī Tâi-gí-tâi** (公視台語台) — PTS Taigi channel
