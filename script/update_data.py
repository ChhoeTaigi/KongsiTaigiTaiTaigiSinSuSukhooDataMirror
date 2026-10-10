"""Mirror the 公視台語台 台語新詞辭庫 (https://www.taigitv.org.tw/taigi-words).

Flow:
1. Crawl every list page (?page=1..N, N read from the pagination) and then
   every entry detail page (/taigi-words/{id}, for 例句 and 相關影音) into a
   temp dir and parse them.
2. Hash the parsed data (the raw HTML carries a per-request CSRF token, so it
   cannot be hashed directly) and compare against public/manifest.json.
3. On change, create public/{YYYYMMDD-HHMM}/ with:
     tangloo/pages/   raw list pages, tangloo/detail/ raw detail pages (gitignored)
     bunji/           KongsiTaigiTaiTaigiSinSuSukhooData.csv / .json
     imtong/          one WAV per reading, named {id}.wav, {id}-2.wav, ...
   Audio whose source URL is unchanged is copied from the previous version
   instead of being downloaded again. 音檔來源網址 points at the GitHub
   Pages copy of each file; 音檔原始網址 keeps the upstream URL. Readings whose
   upstream audio link is dead (HTTP 404) get an empty 音檔 / 音檔來源網址 in
   bunji/ and are listed under "imtong_missing" in manifest.json.
4. Write VERSION_DIFF.md against the previous version.

Options:
  --no-imtong     skip the audio step
  --delay SECS    pause between HTTP requests (default 0.3)
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import requests

try:
    from convert_KongsiTaigiTaiTaigiSinSuSukhooData import (
        apply_mirror_urls, apply_missing_audio, attach_details, parse_page, write_outputs,
    )
    from diff_versions import diff_versions, write_diff_md
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from convert_KongsiTaigiTaiTaigiSinSuSukhooData import (
        apply_mirror_urls, apply_missing_audio, attach_details, parse_page, write_outputs,
    )
    from diff_versions import diff_versions, write_diff_md

SITE = "https://www.taigitv.org.tw"
URL_LIST = f"{SITE}/taigi-words"
USER_AGENT = (
    "Mozilla/5.0 (KongsiTaigiTaiTaigiSinSuSukhooDataMirror; "
    "+https://github.com/ChhoeTaigi/KongsiTaigiTaiTaigiSinSuSukhooDataMirror)"
)

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
MANIFEST_FILE = PUBLIC_DIR / "manifest.json"
DATA_NAME = "KongsiTaigiTaiTaigiSinSuSukhooData"

_PAGE_LINK = re.compile(r"taigi-words\?page=(\d+)")

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def get_timestamp_dir():
    return PUBLIC_DIR / datetime.datetime.now().strftime("%Y%m%d-%H%M")


def fetch(url, retries=3, delay=0.3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=60)
            r.raise_for_status()
            time.sleep(delay)
            return r
        except requests.RequestException as e:
            last_error = e
            status = getattr(e.response, "status_code", None)
            if status is not None and 400 <= status < 500:
                break  # a 404 will not heal on retry
            print(f"  retry {attempt}/{retries} for {url}: {e}")
            time.sleep(delay * 4 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def crawl_pages(pages_dir, delay):
    """Download every list page into pages_dir; return the parsed entries."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {URL_LIST}?page=1 ...")
    first = fetch(f"{URL_LIST}?page=1", delay=delay).text
    (pages_dir / "page_1.html").write_text(first, encoding="utf-8")
    page_numbers = [int(n) for n in _PAGE_LINK.findall(first)]
    last_page = max(page_numbers) if page_numbers else 1
    print(f"Pagination reports {last_page} pages")

    by_id = {}
    for e in parse_page(first):
        by_id.setdefault(e["id"], e)

    for n in range(2, last_page + 1):
        html_text = fetch(f"{URL_LIST}?page={n}", delay=delay).text
        (pages_dir / f"page_{n}.html").write_text(html_text, encoding="utf-8")
        entries = parse_page(html_text)
        for e in entries:
            by_id.setdefault(e["id"], e)
        sys.stdout.write(f"\r  page {n}/{last_page}  entries so far: {len(by_id)}   ")
        sys.stdout.flush()
        if not entries:
            print(f"\n  Warning: page {n} had no entries")
    print()
    return [by_id[k] for k in sorted(by_id)]


def crawl_details(entries, detail_dir, delay):
    """Download every entry's detail page into detail_dir/{id}.html and merge 例句 / 相關影音."""
    detail_dir.mkdir(parents=True, exist_ok=True)
    total = len(entries)
    failed = 0
    for i, e in enumerate(entries, start=1):
        try:
            html_text = fetch(f"{URL_LIST}/{e['id']}", delay=delay).text
        except RuntimeError as err:
            failed += 1
            print(f"\n  Detail failed: {err}")
            continue
        (detail_dir / f"{e['id']}.html").write_text(html_text, encoding="utf-8")
        sys.stdout.write(f"\r  detail {i}/{total}   ")
        sys.stdout.flush()
    print()
    found = attach_details(entries, detail_dir)
    print(f"Detail pages: {found} parsed, {failed} failed")
    return failed


def data_hash(entries):
    """SHA256 of the canonical JSON of the parsed entries."""
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_manifest():
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(data):
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sync_audio(entries, imtong_dir, prev_version_dir, delay):
    """Make sure imtong_dir has every reading's WAV.

    Files are reused from prev_version_dir/imtong when that version recorded
    the same source URL for the same local filename; otherwise downloaded.
    """
    imtong_dir.mkdir(parents=True, exist_ok=True)

    prev_urls = {}
    if prev_version_dir is not None:
        prev_json = prev_version_dir / "bunji" / f"{DATA_NAME}.json"
        if prev_json.exists():
            for e in _load_json(prev_json):
                for r in e.get("音讀", []):
                    if r.get("音檔"):
                        prev_urls[r["音檔"]] = r.get("音檔原始網址", "")

    wanted = [(r["音檔"], r["音檔原始網址"]) for e in entries for r in e["音讀"] if r["音檔"]]
    reused = downloaded = 0
    failed = []
    for i, (name, url) in enumerate(wanted, start=1):
        target = imtong_dir / name
        if target.exists():
            continue
        prev_file = prev_version_dir / "imtong" / name if prev_version_dir else None
        if prev_file is not None and prev_file.exists() and prev_urls.get(name) == url:
            shutil.copy2(prev_file, target)
            reused += 1
            continue
        try:
            r = fetch(url, delay=delay)
            target.write_bytes(r.content)
            downloaded += 1
        except RuntimeError as e:
            failed.append(name)
            print(f"\n  Audio failed: {e}")
        sys.stdout.write(f"\r  audio {i}/{len(wanted)}  reused {reused}  downloaded {downloaded}  failed {len(failed)}   ")
        sys.stdout.flush()
    print(f"\nAudio: {len(wanted)} readings, reused {reused}, downloaded {downloaded}, failed {len(failed)}")
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-imtong", action="store_true", help="skip downloading audio")
    parser.add_argument("--delay", type=float, default=0.3, help="seconds between HTTP requests")
    args = parser.parse_args()

    print("Starting update check...")
    temp_dir = PUBLIC_DIR / "temp_update"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_pages = temp_dir / "pages"
    temp_detail = temp_dir / "detail"

    try:
        entries = crawl_pages(temp_pages, args.delay)
        if not entries:
            raise RuntimeError("No entries parsed; aborting so the mirror is not emptied")
        crawl_details(entries, temp_detail, args.delay)
        new_hash = data_hash(entries)
        print(f"Parsed {len(entries)} entries, data hash {new_hash[:12]}...")

        manifest = load_manifest()
        old_hash = manifest.get("files", {}).get(f"{DATA_NAME}.json")
        prev_name = manifest.get("latest_version_dir")
        prev_version_dir = PUBLIC_DIR / prev_name if prev_name else None
        if prev_version_dir is not None and not prev_version_dir.exists():
            prev_version_dir = None
        target_dir = None

        if old_hash == new_hash and prev_version_dir is not None:
            print("No changes detected.")
            target_dir = prev_version_dir
            tangloo_dir = target_dir / "tangloo"
            for name, temp in (("pages", temp_pages), ("detail", temp_detail)):
                if not (tangloo_dir / name).exists():
                    # tangloo is gitignored; a fresh clone lacks it, so keep this crawl.
                    tangloo_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(temp), str(tangloo_dir / name))
        else:
            print("Change detected." if old_hash else "No existing manifest. Initial import.")
            target_dir = get_timestamp_dir()
            tangloo_dir = target_dir / "tangloo"
            tangloo_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_pages), str(tangloo_dir / "pages"))
            shutil.move(str(temp_detail), str(tangloo_dir / "detail"))
            print(f"Created version directory: {target_dir}")

        bunji_dir = target_dir / "bunji"
        csv_path = bunji_dir / f"{DATA_NAME}.csv"
        json_path = bunji_dir / f"{DATA_NAME}.json"
        apply_mirror_urls(entries, target_dir.name)
        if target_dir != prev_version_dir or not json_path.exists():
            write_outputs(entries, str(csv_path), str(json_path))
        else:
            print(f"Keeping existing {bunji_dir}")

        if target_dir != prev_version_dir:
            save_manifest({
                "last_updated": datetime.datetime.now().isoformat(),
                "latest_version_dir": target_dir.name,
                "entry_count": len(entries),
                "source": {f"{DATA_NAME}.json": {"url": URL_LIST}},
                "files": {f"{DATA_NAME}.json": new_hash},
            })
            print("Updated manifest.json.")

        if not args.no_imtong:
            failed = sync_audio(
                entries, target_dir / "imtong",
                prev_version_dir if target_dir != prev_version_dir else None, args.delay,
            )
            missing = sorted(set(failed), key=lambda n: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", n)])
            # Keep bunji/ truthful: 音檔 names a file that exists in imtong/.
            apply_missing_audio(entries, missing)
            write_outputs(entries, str(csv_path), str(json_path))
            manifest_now = load_manifest()
            if manifest_now.get("latest_version_dir") == target_dir.name:
                manifest_now["imtong_missing"] = missing
                save_manifest(manifest_now)
                print(f"Recorded {len(missing)} missing upstream audio files in manifest.json.")

        if prev_version_dir is not None and target_dir != prev_version_dir:
            prev_json = prev_version_dir / "bunji" / f"{DATA_NAME}.json"
            if prev_json.exists():
                print(f"Comparing {prev_version_dir.name} → {target_dir.name}...")
                diff = diff_versions(str(prev_json), str(json_path))
                write_diff_md(diff, prev_version_dir.name, target_dir.name, str(BASE_DIR / "VERSION_DIFF.md"))
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    print("\nUpdate complete!")
    print(f"Data stored in: {target_dir}")


if __name__ == "__main__":
    main()
