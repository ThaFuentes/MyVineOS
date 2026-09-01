#!/usr/bin/env python3
"""
Import public-domain Bible translations and Strong's lexicon into MariaDB.

Sources (free / legal to bundle locally):
  - KJV, ASV, BBE: scrollmapper/bible_databases (public domain)
  - Strong's: mormon-documentation-project/strongs (derived from public-domain Strong's)

NIV is NOT imported — it is copyrighted (Biblica) and requires a separate license.

Usage (from project root):
  python scripts/import_bible_data.py
  python scripts/import_bible_data.py --translations KJV ASV
  python scripts/import_bible_data.py --strongs-only
  python scripts/import_bible_data.py --skip-download   # use cached files in data/bible/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

SCROLLMAPPER_BASE = (
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json"
)
STRONGS_URL = (
    "https://raw.githubusercontent.com/mormon-documentation-project/strongs/master/strongs.json"
)

TRANSLATION_SOURCES = {
    "KJV": {
        "file": "KJV.json",
        "name": "King James Version",
        "default": True,
    },
    "ASV": {
        "file": "ASV.json",
        "name": "American Standard Version",
        "default": False,
    },
    "BBE": {
        "file": "BBE.json",
        "name": "Bible in Basic English",
        "default": False,
    },
}


def _data_dir() -> str:
    path = os.path.join(PROJECT_ROOT, "data", "bible")
    os.makedirs(path, exist_ok=True)
    return path


def download(url: str, dest: str) -> None:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  Using cached {os.path.basename(dest)}")
        return
    print(f"  Downloading {url} ...")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved {dest} ({os.path.getsize(dest) // 1024} KB)")


def load_json(path: str) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def import_translations(codes: list[str], skip_download: bool = False) -> dict[str, int]:
    from app import create_app
    from app.models.pastoral.bible import import_bible_translation, verses_from_scrollmapper

    app = create_app()
    results = {}
    data_dir = _data_dir()

    with app.app_context():
        for code in codes:
            meta = TRANSLATION_SOURCES.get(code)
            if not meta:
                print(f"Unknown translation code: {code}")
                continue
            local_path = os.path.join(data_dir, meta["file"])
            if not skip_download:
                download(f"{SCROLLMAPPER_BASE}/{meta['file']}", local_path)
            elif not os.path.exists(local_path):
                raise FileNotFoundError(f"Missing cached file: {local_path}")

            print(f"Importing {code} ({meta['name']}) ...")
            raw = load_json(local_path)
            verses = verses_from_scrollmapper(raw)
            count = import_bible_translation(
                code,
                meta["name"],
                verses,
                set_default=meta.get("default", False),
            )
            results[code] = count
            print(f"  -> {count:,} verses")
    return results


def import_strongs(skip_download: bool = False) -> int:
    from app import create_app
    from app.models.pastoral.bible import entries_from_strongs_json, import_strongs_lexicon

    app = create_app()
    data_dir = _data_dir()
    local_path = os.path.join(data_dir, "strongs.json")

    if not skip_download:
        download(STRONGS_URL, local_path)
    elif not os.path.exists(local_path):
        raise FileNotFoundError(f"Missing cached file: {local_path}")

    print("Importing Strong's lexicon ...")
    raw = load_json(local_path)
    entries = entries_from_strongs_json(raw)

    with app.app_context():
        count = import_strongs_lexicon(entries)
    print(f"  -> {count:,} entries")
    return count


def main():
    parser = argparse.ArgumentParser(description="Import public-domain Bible data")
    parser.add_argument(
        "--translations",
        nargs="*",
        default=list(TRANSLATION_SOURCES.keys()),
        help="Translation codes to import (default: KJV ASV BBE)",
    )
    parser.add_argument("--strongs-only", action="store_true", help="Import only Strong's lexicon")
    parser.add_argument("--skip-strongs", action="store_true", help="Skip Strong's import")
    parser.add_argument("--skip-download", action="store_true", help="Use files already in data/bible/")
    args = parser.parse_args()

    print("=" * 60)
    print("Bible data import (public domain only — NIV excluded)")
    print("=" * 60)

    if not args.strongs_only:
        results = import_translations(args.translations, skip_download=args.skip_download)
        if not results:
            print("No translations imported.")
            sys.exit(1)

    if not args.skip_strongs:
        import_strongs(skip_download=args.skip_download)

    print("Done.")


if __name__ == "__main__":
    main()