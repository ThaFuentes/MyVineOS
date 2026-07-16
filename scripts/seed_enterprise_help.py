#!/usr/bin/env python3
"""Seed / refresh enterprise Help pack into the DB and write git JSON pack."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from app.help_content.enterprise_pack import build_enterprise_pack
from app.models.help_pack import import_pack, write_pack_file


def main():
    pack = build_enterprise_pack()
    out = ROOT / "docs" / "help_packs" / "myvine_enterprise_help_v1.json"
    write_pack_file(out, pack)
    print(f"Wrote {out} ({len(pack['categories'])} categories, {len(pack['articles'])} articles)")

    app = create_app()
    with app.app_context():
        stats = import_pack(pack, user_id=1, replace_bodies=True)
        print("Import stats:", stats)


if __name__ == "__main__":
    main()
