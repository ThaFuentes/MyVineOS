# Portable Help packs: export / import / seed.
# Format myvine_help_v1 is slug-based so packs work across databases and git clones.

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymysql

from app.models.db import get_db
from app.routes.help.queries import (
    create_article,
    create_category,
    list_all_articles,
    list_all_categories,
    slugify,
    update_article,
    update_category,
)

FORMAT_ID = "myvine_help_v1"
PACK_VERSION = 1


def _ser_value(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    return v


def build_portable_pack(include_db_ids: bool = False) -> dict:
    """
    Build a git-friendly help pack.
    Articles always include category_slug (not only category_id).
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    categories = list_all_categories(cur)
    articles = list_all_articles(cur)

    id_to_slug = {int(c["id"]): c["slug"] for c in categories if c.get("id") is not None}

    cat_out = []
    for c in categories:
        row = {
            "slug": c.get("slug"),
            "name": c.get("name"),
            "description": c.get("description") or "",
            "sort_order": int(c.get("sort_order") or 0),
            "is_published": 1 if c.get("is_published", 1) else 0,
        }
        if include_db_ids and c.get("id") is not None:
            row["id"] = c["id"]
        cat_out.append(row)

    art_out = []
    for a in articles:
        cid = a.get("category_id")
        cat_slug = a.get("category_slug")
        if not cat_slug and cid is not None:
            cat_slug = id_to_slug.get(int(cid))
        row = {
            "slug": a.get("slug"),
            "title": a.get("title"),
            "summary": a.get("summary") or "",
            "body_md": a.get("body_md") or "",
            "category_slug": cat_slug or "",
            "permission_key": a.get("permission_key") or None,
            "sort_order": int(a.get("sort_order") or 0),
            "is_published": 1 if a.get("is_published", 1) else 0,
        }
        if include_db_ids and a.get("id") is not None:
            row["id"] = a["id"]
            if cid is not None:
                row["category_id"] = cid
        art_out.append(row)

    # Stable order for clean git diffs
    cat_out.sort(key=lambda x: (x.get("sort_order", 0), x.get("slug") or ""))
    art_out.sort(key=lambda x: (x.get("category_slug") or "", x.get("sort_order", 0), x.get("slug") or ""))

    return {
        "format": FORMAT_ID,
        "pack_version": PACK_VERSION,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "title": "MyVineChurch Help Pack",
        "description": (
            "Portable help categories and guides. Import via Help → Manage → Re-upload, "
            "or load from docs/help_packs/ on deploy."
        ),
        "categories": cat_out,
        "articles": art_out,
    }


def pack_to_json(pack: dict | None = None, *, indent: int = 2) -> str:
    pack = pack or build_portable_pack()
    return json.dumps(pack, ensure_ascii=False, indent=indent) + "\n"


def parse_pack(raw: str | bytes | dict) -> dict:
    if isinstance(raw, dict):
        data = raw
    else:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig")
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Help pack must be a JSON object")
    fmt = data.get("format")
    if fmt not in (None, FORMAT_ID, "myvine_help_v1"):
        # Accept unknown format only if categories/articles present
        if not (data.get("categories") or data.get("articles")):
            raise ValueError(f"Unsupported help pack format: {fmt!r}")
    return data


def import_pack(
    data: dict | str | bytes,
    *,
    user_id: int | None = None,
    replace_bodies: bool = True,
) -> dict:
    """
    Merge pack into DB by category/article slug.
    Does not delete guides that are only local.
    Returns stats dict.
    """
    data = parse_pack(data)
    cats = data.get("categories") or []
    arts = data.get("articles") or []

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    created_c = updated_c = created_a = updated_a = skipped = 0
    cat_id_to_slug: dict[int, str] = {}

    for c in cats:
        if not isinstance(c, dict):
            skipped += 1
            continue
        name = (c.get("name") or "").strip()
        slug = slugify(c.get("slug") or name)
        if not name or not slug:
            skipped += 1
            continue
        if c.get("id") is not None:
            try:
                cat_id_to_slug[int(c["id"])] = slug
            except (TypeError, ValueError):
                pass
        clean = {
            "name": name,
            "slug": slug,
            "description": (c.get("description") or "").strip(),
            "sort_order": int(c.get("sort_order") or 0),
            "is_published": 1 if c.get("is_published", 1) else 0,
        }
        cur.execute("SELECT id FROM help_categories WHERE slug = %s", (slug,))
        row = cur.fetchone()
        if row:
            update_category(cur, row["id"] if isinstance(row, dict) else row[0], clean)
            updated_c += 1
        else:
            create_category(cur, clean)
            created_c += 1

    cur.execute("SELECT id, slug FROM help_categories")
    slug_to_id = {}
    for r in cur.fetchall():
        if isinstance(r, dict):
            slug_to_id[r["slug"]] = r["id"]
        else:
            slug_to_id[r[1]] = r[0]

    uid = user_id or 1
    for a in arts:
        if not isinstance(a, dict):
            skipped += 1
            continue
        title = (a.get("title") or "").strip()
        slug = slugify(a.get("slug") or title)
        if not title or not slug:
            skipped += 1
            continue

        cat_slug = (a.get("category_slug") or "").strip()
        if not cat_slug and a.get("category_id") is not None:
            try:
                cat_slug = cat_id_to_slug.get(int(a["category_id"])) or ""
            except (TypeError, ValueError):
                cat_slug = ""
        new_cat_id = slug_to_id.get(cat_slug) if cat_slug else None

        body = a.get("body_md") if a.get("body_md") is not None else a.get("body")
        body = body if body is not None else ""

        clean = {
            "title": title,
            "slug": slug,
            "summary": (a.get("summary") or "").strip(),
            "body_md": body,
            "category_id": new_cat_id,
            "sort_order": int(a.get("sort_order") or 0),
            "is_published": 1 if a.get("is_published", 1) else 0,
            "permission_key": a.get("permission_key") or a.get("required_permission") or None,
        }

        cur.execute("SELECT id, body_md FROM help_articles WHERE slug = %s", (slug,))
        row = cur.fetchone()
        if row:
            aid = row["id"] if isinstance(row, dict) else row[0]
            if not replace_bodies:
                # keep existing body if import body empty
                existing_body = row.get("body_md") if isinstance(row, dict) else row[1]
                if not (clean["body_md"] or "").strip() and existing_body:
                    clean["body_md"] = existing_body
            update_article(cur, aid, clean, uid)
            updated_a += 1
        else:
            create_article(cur, clean, uid)
            created_a += 1

    db.commit()
    return {
        "categories_created": created_c,
        "categories_updated": updated_c,
        "articles_created": created_a,
        "articles_updated": updated_a,
        "skipped": skipped,
        "categories_total": len(cats),
        "articles_total": len(arts),
    }


def write_pack_file(path: str | Path, pack: dict | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack_to_json(pack), encoding="utf-8")
    return path


def load_pack_file(path: str | Path) -> dict:
    return parse_pack(Path(path).read_text(encoding="utf-8"))
