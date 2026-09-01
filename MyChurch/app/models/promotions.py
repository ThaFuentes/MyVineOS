# Ministry Partners showcase (missionaries, prophets, partner ministries).
from __future__ import annotations

import os
import uuid
from typing import Any, Optional

import pymysql
from werkzeug.utils import secure_filename

from app.models.db import get_db

UPLOAD_SUBDIR = 'promotions'
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def promotions_upload_dir(app=None) -> str:
    if app is None:
        from flask import current_app
        app = current_app
    path = os.path.join(app.config['UPLOAD_FOLDER'], UPLOAD_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def allowed_image(filename: str) -> bool:
    return bool(filename) and '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def _dict_cursor():
    db = get_db()
    return db, db.cursor(pymysql.cursors.DictCursor)


def ensure_table():
    """Idempotent table ensure for long-lived processes."""
    try:
        db, cur = _dict_cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS church_promotions (
                id              INT PRIMARY KEY AUTO_INCREMENT,
                title           VARCHAR(200) NOT NULL,
                subtitle        VARCHAR(255) NULL,
                body_text       MEDIUMTEXT NULL,
                image_path      VARCHAR(255) NULL,
                link_url        VARCHAR(500) NULL,
                link_label      VARCHAR(120) NULL,
                badge           VARCHAR(80) NULL,
                is_published    TINYINT(1) NOT NULL DEFAULT 1,
                sort_order      INT NOT NULL DEFAULT 0,
                created_by      INT NULL,
                updated_by      INT NULL,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_promo_pub_sort (is_published, sort_order)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        db.commit()
    except Exception as e:
        print(f'promotions ensure_table: {e}')


def list_promotions(published_only: bool = False) -> list[dict]:
    ensure_table()
    db, cur = _dict_cursor()
    if published_only:
        cur.execute(
            "SELECT * FROM church_promotions WHERE is_published = 1 ORDER BY sort_order ASC, id ASC"
        )
    else:
        cur.execute("SELECT * FROM church_promotions ORDER BY sort_order ASC, id ASC")
    return list(cur.fetchall() or [])


def count_published() -> int:
    ensure_table()
    try:
        db, cur = _dict_cursor()
        cur.execute("SELECT COUNT(*) AS c FROM church_promotions WHERE is_published = 1")
        row = cur.fetchone() or {}
        return int(row.get('c') or 0)
    except Exception:
        return 0


def get_promotion(promo_id: int) -> Optional[dict]:
    ensure_table()
    db, cur = _dict_cursor()
    cur.execute("SELECT * FROM church_promotions WHERE id = %s", (promo_id,))
    return cur.fetchone()


def next_sort_order() -> int:
    db, cur = _dict_cursor()
    cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM church_promotions")
    row = cur.fetchone() or {}
    return int(row.get('n') or 1)


def save_image(file_storage, app=None) -> Optional[str]:
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        raise ValueError('Image must be png, jpg, jpeg, gif, or webp.')
    base = secure_filename(file_storage.filename)
    name, ext = os.path.splitext(base)
    filename = f"{uuid.uuid4().hex[:12]}_{name[:40]}{ext.lower()}"
    dest = os.path.join(promotions_upload_dir(app), filename)
    file_storage.save(dest)
    return filename


def delete_image_file(filename: str, app=None) -> None:
    if not filename:
        return
    try:
        path = os.path.join(promotions_upload_dir(app), filename)
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def create_promotion(data: dict, user_id: int) -> int:
    ensure_table()
    db, cur = _dict_cursor()
    sort_order = data.get('sort_order')
    if sort_order is None:
        sort_order = next_sort_order()
    cur.execute(
        """
        INSERT INTO church_promotions
            (title, subtitle, body_text, image_path, link_url, link_label, badge,
             is_published, sort_order, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            (data.get('title') or 'Untitled').strip()[:200],
            (data.get('subtitle') or '').strip()[:255] or None,
            (data.get('body_text') or '').strip() or None,
            data.get('image_path') or None,
            (data.get('link_url') or '').strip()[:500] or None,
            (data.get('link_label') or '').strip()[:120] or None,
            (data.get('badge') or '').strip()[:80] or None,
            1 if data.get('is_published', True) else 0,
            int(sort_order),
            user_id,
            user_id,
        ),
    )
    db.commit()
    return int(cur.lastrowid)


def update_promotion(promo_id: int, data: dict, user_id: int) -> bool:
    ensure_table()
    db, cur = _dict_cursor()
    fields = []
    vals = []
    mapping = {
        'title': lambda v: (v or '').strip()[:200],
        'subtitle': lambda v: (v or '').strip()[:255] or None,
        'body_text': lambda v: (v or '').strip() or None,
        'image_path': lambda v: v or None,
        'link_url': lambda v: (v or '').strip()[:500] or None,
        'link_label': lambda v: (v or '').strip()[:120] or None,
        'badge': lambda v: (v or '').strip()[:80] or None,
        'is_published': lambda v: 1 if v else 0,
        'sort_order': lambda v: int(v),
    }
    for key, fn in mapping.items():
        if key in data:
            fields.append(f'{key} = %s')
            vals.append(fn(data[key]))
    if not fields:
        return False
    fields.append('updated_by = %s')
    vals.append(user_id)
    vals.append(promo_id)
    cur.execute(
        f"UPDATE church_promotions SET {', '.join(fields)} WHERE id = %s",
        vals,
    )
    db.commit()
    return cur.rowcount > 0


def delete_promotion(promo_id: int, app=None) -> bool:
    ensure_table()
    row = get_promotion(promo_id)
    if not row:
        return False
    if row.get('image_path'):
        delete_image_file(row['image_path'], app=app)
    db, cur = _dict_cursor()
    cur.execute("DELETE FROM church_promotions WHERE id = %s", (promo_id,))
    db.commit()
    return True


def reorder_promotion(promo_id: int, direction: str) -> bool:
    """Swap sort_order with neighbor (up = lower sort_order first)."""
    ensure_table()
    db, cur = _dict_cursor()
    cur.execute("SELECT id, sort_order FROM church_promotions WHERE id = %s", (promo_id,))
    current = cur.fetchone()
    if not current:
        return False
    if direction == 'up':
        cur.execute(
            """
            SELECT id, sort_order FROM church_promotions
            WHERE sort_order < %s ORDER BY sort_order DESC, id DESC LIMIT 1
            """,
            (current['sort_order'],),
        )
    else:
        cur.execute(
            """
            SELECT id, sort_order FROM church_promotions
            WHERE sort_order > %s ORDER BY sort_order ASC, id ASC LIMIT 1
            """,
            (current['sort_order'],),
        )
    neighbor = cur.fetchone()
    if not neighbor:
        return False
    cur.execute(
        "UPDATE church_promotions SET sort_order = %s WHERE id = %s",
        (neighbor['sort_order'], current['id']),
    )
    cur.execute(
        "UPDATE church_promotions SET sort_order = %s WHERE id = %s",
        (current['sort_order'], neighbor['id']),
    )
    db.commit()
    return True


def get_page_meta() -> dict[str, Any]:
    """Optional page title/intro from settings (empty = use defaults / hide intro)."""
    try:
        db, cur = _dict_cursor()
        cur.execute(
            "SELECT promotions_page_title, promotions_page_intro FROM settings WHERE id = 1"
        )
        row = cur.fetchone() or {}
        return {
            'page_title': (row.get('promotions_page_title') or '').strip(),
            'page_intro': (row.get('promotions_page_intro') or '').strip(),
        }
    except Exception:
        return {'page_title': '', 'page_intro': ''}


def save_page_meta(title: str, intro: str) -> None:
    db, cur = _dict_cursor()
    # Ensure columns
    try:
        cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
              AND COLUMN_NAME IN ('promotions_page_title', 'promotions_page_intro')
        """)
        have = {r['COLUMN_NAME'] for r in (cur.fetchall() or [])}
        if 'promotions_page_title' not in have:
            cur.execute("ALTER TABLE settings ADD COLUMN promotions_page_title VARCHAR(200) NULL")
        if 'promotions_page_intro' not in have:
            cur.execute("ALTER TABLE settings ADD COLUMN promotions_page_intro MEDIUMTEXT NULL")
        db.commit()
    except Exception as e:
        print(f'promotions page meta columns: {e}')
    cur.execute(
        """
        UPDATE settings SET promotions_page_title = %s, promotions_page_intro = %s
        WHERE id = 1
        """,
        ((title or '').strip()[:200] or None, (intro or '').strip() or None),
    )
    db.commit()


def is_promotions_visible() -> bool:
    """Module on + at least one published card."""
    try:
        from app.models.module_toggles import is_module_enabled, get_module_toggles
        if not is_module_enabled('promotions', get_module_toggles()):
            return False
        return count_published() > 0
    except Exception:
        return False
