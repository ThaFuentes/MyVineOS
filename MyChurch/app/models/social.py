# Follow/block, DMs, photos, links, posts, badges, stats.

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime

import pymysql
from flask import current_app, g, has_request_context, session, url_for
from werkzeug.utils import secure_filename

from app.models.db import get_db
from app.utils.appearance import sanitize_public_href
from app.utils.helpers import contains_censored_word
from app.utils.html_sanitize import sanitize_plain_text

HEX = re.compile(r'^#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$')
COLOR_NAME = re.compile(r'^[A-Za-z]{3,24}$')
PHOTO_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_MESSAGE_LEN = 4000
LINK_KINDS = (
    'prayer', 'sermon', 'book', 'dream', 'prophecy', 'event',
    'blog', 'announcement', 'website', 'video', 'other',
)
TAG_LABELS = {
    'prayer': 'Prayer',
    'sermon': 'Sermon',
    'book': 'Book',
    'dream': 'Dream',
    'prophecy': 'Prophecy',
    'event': 'Event',
    'blog': 'Blog',
    'announcement': 'Update',
    'website': 'Link',
    'video': 'Video',
    'other': 'Link',
    'post': 'Post',
    'badge': 'Badge',
    'comment': 'Comment',
}
OWNER_TYPES = ('church', 'campus', 'member')


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def hex_or_none(value: str | None) -> str | None:
    return color_or_none(value)


def color_or_none(value: str | None) -> str | None:
    raw = (value or '').strip()
    if not raw:
        return None
    if COLOR_NAME.match(raw):
        return raw.lower()
    if HEX.match(raw):
        return raw if raw.startswith('#') else f'#{raw}'
    return None


def banner_focus(row: dict | None) -> tuple[int, int]:
    row = row or {}
    x, y = row.get('banner_x'), row.get('banner_y')
    try:
        if x is not None and y is not None:
            return max(0, min(100, int(x))), max(0, min(100, int(y)))
    except (TypeError, ValueError):
        pass
    pos = (row.get('banner_pos') or 'center').strip().lower()
    ymap = {'top': 12, 'center': 50, 'bottom': 88}
    return 50, ymap.get(pos, 50)


def palette_style(row: dict | None) -> str:
    row = row or {}
    parts = []
    if hex_or_none(row.get('accent_color')):
        parts.append(f"--primary:{row['accent_color']}")
        parts.append(f"--profile-serve-on:{row['accent_color']}")
    if hex_or_none(row.get('bg_color')):
        parts.append(f"--profile-bg:{row['bg_color']}")
    if hex_or_none(row.get('text_color')):
        parts.append(f"--profile-text:{row['text_color']}")
    return ';'.join(parts)


def blocked_either_way(a: int | None, b: int | None) -> bool:
    if not a or not b or int(a) == int(b):
        return False
    cur = _cur()
    cur.execute(
        """
        SELECT 1 FROM user_blocks
        WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)
        LIMIT 1
        """,
        (int(a), int(b), int(b), int(a)),
    )
    return bool(cur.fetchone())


def is_following(follower_id: int, followed_id: int) -> bool:
    cur = _cur()
    cur.execute(
        "SELECT 1 FROM user_follows WHERE follower_id=%s AND followed_id=%s",
        (int(follower_id), int(followed_id)),
    )
    return bool(cur.fetchone())


def follow_counts(user_id: int) -> dict:
    cur = _cur()
    cur.execute("SELECT COUNT(*) AS n FROM user_follows WHERE followed_id=%s", (int(user_id),))
    followers = int((cur.fetchone() or {}).get('n') or 0)
    cur.execute("SELECT COUNT(*) AS n FROM user_follows WHERE follower_id=%s", (int(user_id),))
    following = int((cur.fetchone() or {}).get('n') or 0)
    return {'followers': followers, 'following': following}


def set_follow(follower_id: int, followed_id: int, follow: bool) -> None:
    if int(follower_id) == int(followed_id):
        return
    if blocked_either_way(follower_id, followed_id):
        return
    db = get_db()
    cur = db.cursor()
    if follow:
        cur.execute(
            "INSERT IGNORE INTO user_follows (follower_id, followed_id) VALUES (%s,%s)",
            (int(follower_id), int(followed_id)),
        )
    else:
        cur.execute(
            "DELETE FROM user_follows WHERE follower_id=%s AND followed_id=%s",
            (int(follower_id), int(followed_id)),
        )
    db.commit()


def set_block(blocker_id: int, blocked_id: int, block: bool) -> None:
    if int(blocker_id) == int(blocked_id):
        return
    db = get_db()
    cur = db.cursor()
    if block:
        cur.execute(
            "INSERT IGNORE INTO user_blocks (blocker_id, blocked_id) VALUES (%s,%s)",
            (int(blocker_id), int(blocked_id)),
        )
        cur.execute(
            """
            DELETE FROM user_follows
            WHERE (follower_id=%s AND followed_id=%s) OR (follower_id=%s AND followed_id=%s)
            """,
            (int(blocker_id), int(blocked_id), int(blocked_id), int(blocker_id)),
        )
    else:
        cur.execute(
            "DELETE FROM user_blocks WHERE blocker_id=%s AND blocked_id=%s",
            (int(blocker_id), int(blocked_id)),
        )
    db.commit()


def list_links(owner_type: str, owner_id: int, kind: str | None = None) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM page_links WHERE owner_type=%s AND owner_id=%s"
    args: list = [owner_type, int(owner_id)]
    if kind:
        sql += " AND kind=%s"
        args.append(kind)
    sql += " ORDER BY sort_order ASC, id DESC"
    try:
        cur.execute(sql, args)
        return list(cur.fetchall() or [])
    except Exception:
        return []


def add_link(owner_type: str, owner_id: int, kind: str, title: str, url: str, note: str, user_id: int | None) -> int | None:
    title = sanitize_plain_text(title)[:255]
    note = sanitize_plain_text(note)[:500]
    href = sanitize_public_href(url)
    kind = kind if kind in LINK_KINDS else 'website'
    if not title and href:
        title = href.split('//', 1)[-1].split('/', 1)[0].replace('www.', '')[:255]
    if not title or contains_censored_word(f'{title} {note}'):
        return None
    if kind != 'book' and not href:
        return None
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO page_links (owner_type, owner_id, kind, title, url, note, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (owner_type, int(owner_id), kind, title, href or None, note or None, user_id),
    )
    db.commit()
    return cur.lastrowid


def delete_link(link_id: int, owner_type: str, owner_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM page_links WHERE id=%s AND owner_type=%s AND owner_id=%s",
        (int(link_id), owner_type, int(owner_id)),
    )
    db.commit()


def photo_limit(owner_type: str) -> int:
    settings = getattr(g, 'settings', None) or {} if has_request_context() else {}
    if owner_type in ('church', 'campus'):
        try:
            return int(settings.get('church_photo_limit') or 0)
        except (TypeError, ValueError):
            return 0
    try:
        return int(settings.get('member_photo_limit') or 12)
    except (TypeError, ValueError):
        return 12


def photo_count(owner_type: str, owner_id: int) -> int:
    cur = _cur()
    try:
        cur.execute(
            "SELECT COUNT(*) AS n FROM page_photos WHERE owner_type=%s AND owner_id=%s",
            (owner_type, int(owner_id)),
        )
        return int((cur.fetchone() or {}).get('n') or 0)
    except Exception:
        return 0


def list_photos(owner_type: str, owner_id: int, limit: int | None = None) -> list[dict]:
    cur = _cur()
    try:
        sql = """
            SELECT * FROM page_photos
            WHERE owner_type=%s AND owner_id=%s
            ORDER BY id DESC
        """
        args: list = [owner_type, int(owner_id)]
        if limit:
            sql += " LIMIT %s"
            args.append(int(limit))
        cur.execute(sql, args)
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    for row in rows:
        row['url'] = url_for('church.serve_photo', photo_id=row['id'])
        row['view_url'] = url_for('church.photo_view', photo_id=row['id'])
    return rows


def _photo_dir():
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'page_photos')
    os.makedirs(path, exist_ok=True)
    return path


def add_photo(owner_type: str, owner_id: int, file_storage, caption: str, user_id: int | None) -> tuple[bool, str]:
    limit = photo_limit(owner_type)
    if limit and photo_count(owner_type, owner_id) >= limit:
        return False, f'Photo limit reached ({limit}).'
    if not file_storage or not file_storage.filename:
        return False, 'Choose a photo.'
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in PHOTO_EXT:
        return False, 'Use png, jpg, gif, or webp.'
    cap = sanitize_plain_text(caption)[:255]
    if contains_censored_word(cap):
        return False, 'Caption contains a prohibited word.'
    name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(_photo_dir(), name)
    file_storage.save(dest)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO page_photos (owner_type, owner_id, filename, caption, created_by)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (owner_type, int(owner_id), name, cap or None, user_id),
    )
    db.commit()
    return True, 'Photo added.'


def get_photo(photo_id: int) -> dict | None:
    cur = _cur()
    cur.execute("SELECT * FROM page_photos WHERE id=%s", (int(photo_id),))
    return cur.fetchone()


def identity_dir():
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'identity')
    os.makedirs(path, exist_ok=True)
    return path


def identity_url(filename: str | None) -> str:
    if not filename:
        return ''
    if str(filename).startswith('http') or str(filename).startswith('/'):
        return filename
    return url_for('church.serve_identity', filename=filename)


def save_identity_file(file_storage, prefix: str) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in PHOTO_EXT:
        return None
    name = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
    file_storage.save(os.path.join(identity_dir(), name))
    return name


def set_member_identity(user_id: int, slot: str, file_storage) -> tuple[bool, str]:
    col = 'photo_path' if slot == 'avatar' else 'banner_path'
    name = save_identity_file(file_storage, f"u{int(user_id)}_{slot}")
    if not name:
        return False, 'Use png, jpg, gif, or webp.'
    db = get_db()
    cur = db.cursor()
    cur.execute(f"UPDATE member_spaces SET {col}=%s WHERE user_id=%s", (name, int(user_id)))
    db.commit()
    return True, 'Saved.'


def set_church_identity(campus_id: int, slot: str, file_storage, user_id: int | None) -> tuple[bool, str]:
    col = 'portrait_path' if slot == 'avatar' else 'hero_path'
    name = save_identity_file(file_storage, f"c{int(campus_id)}_{slot}")
    if not name:
        return False, 'Use png, jpg, gif, or webp.'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"""
        INSERT INTO church_pages (campus_id, {col}, updated_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE {col}=VALUES({col}), updated_by=VALUES(updated_by)
        """,
        (int(campus_id or 0), name, user_id),
    )
    db.commit()
    return True, 'Saved.'


def set_banner_focus(scope: str, owner_id: int, x: int, y: int) -> None:
    x = max(0, min(100, int(x)))
    y = max(0, min(100, int(y)))
    db = get_db()
    cur = db.cursor()
    if scope == 'church':
        cur.execute(
            """
            INSERT INTO church_pages (campus_id, banner_x, banner_y)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE banner_x=VALUES(banner_x), banner_y=VALUES(banner_y)
            """,
            (int(owner_id or 0), x, y),
        )
    else:
        cur.execute(
            "UPDATE member_spaces SET banner_x=%s, banner_y=%s WHERE user_id=%s",
            (x, y, int(owner_id)),
        )
    db.commit()


def tag_label(kind: str | None) -> str:
    k = (kind or '').strip().lower()
    return TAG_LABELS.get(k, (k or 'Link').title())


def delete_photo(photo_id: int, owner_type: str, owner_id: int) -> None:
    row = get_photo(photo_id)
    if not row or row.get('owner_type') != owner_type or int(row.get('owner_id') or 0) != int(owner_id):
        return
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM page_photos WHERE id=%s", (int(photo_id),))
    db.commit()
    path = os.path.join(_photo_dir(), secure_filename(row.get('filename') or ''))
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def create_post(user_id: int, kind: str, title: str, body: str, url: str, visibility: str, image_path: str | None = None) -> int | None:
    title = sanitize_plain_text(title or '')[:255]
    body = sanitize_plain_text(body or '')[:8000]
    href = sanitize_public_href(url)
    if kind not in ('post', 'blog', 'book', 'quote', 'verse', 'image'):
        kind = 'post'
    if visibility not in ('public', 'private', 'personal', 'followers'):
        visibility = 'public'
    if not title:
        if kind == 'quote':
            title = 'Quote'
        elif kind == 'verse':
            title = 'Verse'
        elif kind == 'image':
            title = 'Photo'
        elif body:
            title = body[:80]
        else:
            title = 'Post'
    if contains_censored_word(f'{title} {body}'):
        return None
    if not body and not href and not image_path and kind != 'post':
        return None
    if kind == 'post' and not body and not href and not image_path:
        return None
    db = get_db()
    cur = db.cursor()
    args = (int(user_id), kind, title, body or None, href or None, visibility, image_path or None)
    try:
        cur.execute(
            """
            INSERT INTO community_posts (user_id, kind, title, body, url, visibility, image_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            args,
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO community_posts (user_id, kind, title, body, url, visibility)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            args[:6],
        )
    db.commit()
    return cur.lastrowid


WALL_POST_KINDS = ('post', 'quote', 'verse', 'image', 'book', 'blog')


def _post_visibility_sql(alias: str = 'p', viewer_id: int | None = None, as_mod: bool = False) -> tuple[str, list]:
    parts = [f'{alias}.removed_at IS NULL']
    args: list = []
    if as_mod:
        return ' AND '.join(parts), args
    if viewer_id:
        parts.append(f'(COALESCE({alias}.shadowed,0)=0 OR {alias}.user_id=%s)')
        args.append(int(viewer_id))
    else:
        parts.append(f'COALESCE({alias}.shadowed,0)=0')
    return ' AND '.join(parts), args


def _viewer_is_wall_mod() -> bool:
    try:
        from app.models.moderation import can_moderate_walls
        return bool(can_moderate_walls())
    except Exception:
        return False


def list_posts_by_voice(posted_as: str, campus_id: int = 0, limit: int = 20, viewer_id: int | None = None) -> list[dict]:
    """Compose posts stamped as church or a branch — not personal member posts."""
    voice = (posted_as or '').strip()
    if voice not in ('church', 'campus'):
        return []
    cur = _cur()
    kinds = WALL_POST_KINDS
    placeholders = ",".join(["%s"] * len(kinds))
    vis_sql, vis_args = _post_visibility_sql('p', viewer_id, as_mod=_viewer_is_wall_mod())
    sql = f"""
        SELECT p.*, u.username, cp.posted_as, cp.campus_id AS post_campus
        FROM community_posts p
        INNER JOIN content_posting cp
          ON cp.content_id = p.id AND cp.content_type = p.kind
        LEFT JOIN users u ON u.id = p.user_id
        WHERE cp.posted_as = %s
          AND p.kind IN ({placeholders})
          AND {vis_sql}
    """
    args: list = [voice, *kinds, *vis_args]
    if voice == 'campus':
        sql += " AND cp.campus_id = %s"
        args.append(int(campus_id or 0))
    sql += " ORDER BY p.created_at DESC LIMIT %s"
    args.append(int(limit))
    try:
        cur.execute(sql, args)
        return list(cur.fetchall() or [])
    except Exception:
        return []


def get_community_post(post_id: int) -> dict | None:
    cur = _cur()
    try:
        cur.execute("SELECT * FROM community_posts WHERE id=%s", (int(post_id),))
        return cur.fetchone()
    except Exception:
        return None


def delete_post(post_id: int, actor_id: int) -> tuple[bool, str]:
    row = get_community_post(post_id)
    if not row:
        return False, 'That post is gone.'
    kind = (row.get('kind') or 'post').strip()
    if kind not in WALL_POST_KINDS:
        return False, 'That post cannot be removed from the wall.'
    actor = int(actor_id)
    owner = int(row.get('user_id') or 0)
    allowed = owner == actor
    if not allowed:
        try:
            from app.models import church_community as cc
            mapped = cc.get_postings([((row.get('kind') or 'post'), int(post_id))])
            meta = mapped.get(((row.get('kind') or 'post'), int(post_id))) or {}
            if (meta.get('posted_as') or '') in ('church', 'campus') and cc.can_edit_church_page(
                int(meta.get('campus_id') or 0)
            ):
                allowed = True
        except Exception:
            allowed = False
    if not allowed:
        return False, 'You can only delete your own posts.'
    image = (row.get('image_path') or '').strip()
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM community_posts WHERE id=%s", (int(post_id),))
    try:
        cur.execute(
            "DELETE FROM content_posting WHERE content_type=%s AND content_id=%s",
            (row.get('kind') or 'post', int(post_id)),
        )
    except Exception:
        pass
    db.commit()
    if image:
        path = os.path.join(identity_dir(), image) if not os.path.isabs(image) else image
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return True, 'Post removed.'


def following_ids(user_id: int | None) -> list[int]:
    if not user_id:
        return []
    cur = _cur()
    try:
        cur.execute(
            "SELECT followed_id FROM user_follows WHERE follower_id=%s",
            (int(user_id),),
        )
        return [int(r['followed_id']) for r in (cur.fetchall() or []) if r.get('followed_id')]
    except Exception:
        return []


def post_visible_to(
    row: dict,
    viewer_id: int | None,
    viewer_follows: set[int] | None = None,
    surface: str = 'feed',
) -> bool:
    """public = anyone; private = signed-in; personal = owner, and only on their wall."""
    vis = (row.get('visibility') or 'public').strip()
    author = int(row.get('user_id') or row.get('author_id') or 0)
    is_owner = bool(viewer_id and author and int(viewer_id) == author)
    if vis == 'personal':
        return is_owner and surface == 'wall'
    if is_owner:
        return True
    if vis == 'public':
        return True
    if not viewer_id:
        return False
    if vis == 'private':
        return True
    if vis == 'followers':
        return bool(viewer_follows and author in viewer_follows)
    return False


def _decorate_post_row(row: dict) -> dict:
    row['image_url'] = identity_url(row.get('image_path'))
    row['display_name'] = _person_name(row)
    username = (row.get('username') or '').strip()
    row['author_url'] = url_for('church.member_page', username=username) if username else ''
    row['shadowed'] = bool(row.get('shadowed'))
    return row


def list_posts_by_users(user_ids: list[int], viewer_id: int | None = None, limit: int = 24) -> list[dict]:
    ids = [int(i) for i in user_ids if i]
    if not ids:
        return []
    cur = _cur()
    kinds = WALL_POST_KINDS
    ph_ids = ",".join(["%s"] * len(ids))
    ph_kinds = ",".join(["%s"] * len(kinds))
    vis_sql, vis_args = _post_visibility_sql('p', viewer_id, as_mod=_viewer_is_wall_mod())
    try:
        cur.execute(
            f"""
            SELECT p.*, u.username, u.first_name, u.last_name, u.primary_campus_id
            FROM community_posts p
            LEFT JOIN users u ON u.id = p.user_id
            WHERE p.user_id IN ({ph_ids})
              AND p.kind IN ({ph_kinds})
              AND {vis_sql}
            ORDER BY p.created_at DESC
            LIMIT %s
            """,
            (*ids, *kinds, *vis_args, max(int(limit) * 2, 8)),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    follows = set(following_ids(viewer_id)) if viewer_id else set()
    out = []
    for row in rows:
        if viewer_id and blocked_either_way(viewer_id, row.get('user_id')):
            continue
        if not post_visible_to(row, viewer_id, follows, surface='wall'):
            continue
        out.append(_decorate_post_row(row))
        if len(out) >= int(limit):
            break
    return out


def list_recent_wall_posts(viewer_id: int | None = None, limit: int = 40) -> list[dict]:
    cur = _cur()
    kinds = WALL_POST_KINDS
    ph_kinds = ",".join(["%s"] * len(kinds))
    vis_sql, vis_args = _post_visibility_sql('p', viewer_id, as_mod=_viewer_is_wall_mod())
    try:
        cur.execute(
            f"""
            SELECT p.*, u.username, u.first_name, u.last_name, u.primary_campus_id
            FROM community_posts p
            LEFT JOIN users u ON u.id = p.user_id
            WHERE p.kind IN ({ph_kinds})
              AND {vis_sql}
            ORDER BY p.created_at DESC
            LIMIT %s
            """,
            (*kinds, *vis_args, max(int(limit) * 3, 12)),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    follows = set(following_ids(viewer_id)) if viewer_id else set()
    out = []
    for row in rows:
        if viewer_id and blocked_either_way(viewer_id, row.get('user_id')):
            continue
        if not post_visible_to(row, viewer_id, follows, surface='feed'):
            continue
        out.append(_decorate_post_row(row))
        if len(out) >= int(limit):
            break
    return out


def following_preview(user_id: int, viewer_id: int | None = None, limit: int = 10) -> list[dict]:
    ids = following_ids(user_id)
    if not ids:
        return []
    cur = _cur()
    ph = ",".join(["%s"] * len(ids))
    try:
        cur.execute(
            f"""
            SELECT u.id, u.username, u.first_name, u.last_name,
                   m.photo_path, m.page_private, m.show_to_visitors, m.show_in_directory
            FROM users u
            LEFT JOIN member_spaces m ON m.user_id = u.id
            WHERE u.id IN ({ph})
            ORDER BY u.first_name ASC, u.last_name ASC
            LIMIT %s
            """,
            (*ids, int(limit)),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    out = []
    for row in rows:
        uid = int(row.get('id') or 0)
        if viewer_id and blocked_either_way(viewer_id, uid):
            continue
        if row.get('page_private') and (not viewer_id or int(viewer_id) != uid):
            continue
        if not viewer_id and not row.get('show_to_visitors'):
            continue
        name = _person_name(row)
        username = (row.get('username') or '').strip()
        out.append({
            'id': uid,
            'username': username,
            'display_name': name,
            'pic_url': identity_url(row.get('photo_path')),
            'page_url': url_for('church.member_page', username=username) if username else '',
            'initials': _initials(name),
        })
    return out


def list_posts(user_id: int | None = None, limit: int = 20, kinds=None) -> list[dict]:
    cur = _cur()
    vis_sql, vis_args = _post_visibility_sql('p', user_id, as_mod=_viewer_is_wall_mod())
    sql = f"SELECT p.*, u.username FROM community_posts p LEFT JOIN users u ON u.id=p.user_id WHERE {vis_sql}"
    args: list = list(vis_args)
    if user_id:
        sql += " AND p.user_id=%s"
        args.append(int(user_id))
    if kinds:
        sql += " AND p.kind IN (" + ",".join(["%s"] * len(kinds)) + ")"
        args.extend(kinds)
    sql += " ORDER BY p.created_at DESC LIMIT %s"
    args.append(int(limit))
    try:
        cur.execute(sql, args)
        return list(cur.fetchall() or [])
    except Exception:
        return []


def award_badge(user_id: int, series_id: int, badge_kind: str, title: str = '') -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT IGNORE INTO member_badges (user_id, series_id, badge_kind)
        VALUES (%s,%s,%s)
        """,
        (int(user_id), int(series_id), badge_kind),
    )
    db.commit()
    return cur.rowcount == 1


def list_badges(user_id: int) -> list[dict]:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT b.*, s.title AS series_title
            FROM member_badges b
            LEFT JOIN curriculum_series s ON s.id = b.series_id
            WHERE b.user_id=%s
            ORDER BY b.created_at DESC
            """,
            (int(user_id),),
        )
        return list(cur.fetchall() or [])
    except Exception:
        return []


def hour_message_count(user_id: int) -> int:
    cur = _cur()
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM dm_messages
        WHERE sender_id=%s AND created_at >= (NOW() - INTERVAL 1 HOUR)
        """,
        (int(user_id),),
    )
    return int((cur.fetchone() or {}).get('n') or 0)


def _person_name(row: dict | None) -> str:
    row = row or {}
    name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
    return name or (row.get('username') or '').strip() or 'Member'


def _initials(name: str) -> str:
    parts = [p for p in (name or '').split() if p]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def _preview_text(text: str, limit: int = 88) -> str:
    compact = ' '.join((text or '').split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + '…'


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace('Z', ''))
    except Exception:
        return None


def when_label(value) -> str:
    dt = _parse_dt(value)
    if not dt:
        return ''
    try:
        from app.utils.time_utils import now_church, to_church_local
        local = to_church_local(dt)
        now = now_church()
    except Exception:
        local = dt
        now = datetime.now()
    if local.tzinfo and now.tzinfo is None:
        now = now.replace(tzinfo=local.tzinfo)
    elif now.tzinfo and local.tzinfo is None:
        local = local.replace(tzinfo=now.tzinfo)
    try:
        secs = int((now - local).total_seconds())
    except Exception:
        return local.strftime('%b %d')
    if secs < 45:
        return 'Just now'
    if secs < 3600:
        mins = max(1, secs // 60)
        return f'{mins} min ago'
    if local.date() == now.date():
        return local.strftime('%-I:%M %p')
    if (now.date() - local.date()).days == 1:
        return 'Yesterday'
    if (now.date() - local.date()).days < 7:
        return local.strftime('%a')
    if local.year == now.year:
        return local.strftime('%b %-d')
    return local.strftime('%b %-d, %Y')


def message_when(value) -> str:
    dt = _parse_dt(value)
    if not dt:
        return ''
    try:
        from app.utils.time_utils import now_church, to_church_local
        local = to_church_local(dt)
        now = now_church()
    except Exception:
        local = dt
        now = datetime.now()
    if local.tzinfo and now.tzinfo is None:
        now = now.replace(tzinfo=local.tzinfo)
    elif now.tzinfo and local.tzinfo is None:
        local = local.replace(tzinfo=now.tzinfo)
    stamp = local.strftime('%-I:%M %p')
    if local.date() == now.date():
        return stamp
    if local.year == now.year:
        return f"{local.strftime('%b %-d')} · {stamp}"
    return f"{local.strftime('%b %-d, %Y')} · {stamp}"


def church_portrait_url(campus_id: int = 0) -> str:
    cur = _cur()
    try:
        cur.execute(
            "SELECT portrait_path FROM church_pages WHERE campus_id=%s",
            (int(campus_id or 0),),
        )
        row = cur.fetchone() or {}
        return identity_url(row.get('portrait_path'))
    except Exception:
        return ''


def _member_portraits(user_ids: list[int]) -> dict[int, str]:
    ids = [int(i) for i in user_ids if i]
    if not ids:
        return {}
    cur = _cur()
    placeholders = ",".join(["%s"] * len(ids))
    try:
        cur.execute(
            f"""
            SELECT user_id, photo_path FROM member_spaces
            WHERE user_id IN ({placeholders})
              AND photo_path IS NOT NULL AND photo_path != ''
            """,
            ids,
        )
    except Exception:
        return {}
    out = {}
    for row in cur.fetchall() or []:
        out[int(row['user_id'])] = identity_url(row.get('photo_path'))
    return out


def _last_messages(thread_ids: list[int]) -> dict[int, dict]:
    from app.utils.dm_crypto import decrypt_dm

    ids = [int(i) for i in thread_ids if i]
    if not ids:
        return {}
    cur = _cur()
    placeholders = ",".join(["%s"] * len(ids))
    cur.execute(
        f"""
        SELECT m.thread_id, m.sender_id, m.body_enc, m.created_at
        FROM dm_messages m
        INNER JOIN (
            SELECT thread_id, MAX(id) AS max_id
            FROM dm_messages
            WHERE thread_id IN ({placeholders})
            GROUP BY thread_id
        ) latest ON latest.max_id = m.id
        """,
        ids,
    )
    out = {}
    for row in cur.fetchall() or []:
        body = decrypt_dm(row.get('body_enc') or '')
        out[int(row['thread_id'])] = {
            'sender_id': int(row['sender_id'] or 0),
            'body': body,
            'preview': _preview_text(body),
            'created_at': row.get('created_at'),
        }
    return out


def thread_read_at(thread: dict | None, user_id: int):
    if not thread or not user_id:
        return None
    uid = int(user_id)
    if is_room_thread(thread):
        row = membership(int(thread['id']), uid)
        return (row or {}).get('last_read_at')
    if is_church_thread(thread):
        starter = int(thread.get('starter_id') or thread.get('user_low') or 0)
        if uid == starter:
            return thread.get('last_read_at_low')
        return thread.get('last_read_at_high')
    if uid == int(thread.get('user_low') or 0):
        return thread.get('last_read_at_low')
    return thread.get('last_read_at_high')


def is_church_thread(thread: dict | None) -> bool:
    if not thread:
        return False
    if (thread.get('thread_kind') or 'direct') == 'church':
        return True
    return int(thread.get('user_high') or 0) == 0 and (thread.get('thread_kind') or '') not in ('direct', 'group', 'open')


def is_room_thread(thread: dict | None) -> bool:
    return (thread.get('thread_kind') or '') in ('group', 'open') if thread else False


def membership(thread_id: int, user_id: int) -> dict | None:
    cur = _cur()
    try:
        cur.execute(
            "SELECT * FROM dm_members WHERE thread_id=%s AND user_id=%s",
            (int(thread_id), int(user_id)),
        )
        return cur.fetchone()
    except Exception:
        return None


def user_can_use_thread(thread: dict | None, user_id: int) -> bool:
    if not thread or not user_id:
        return False
    uid = int(user_id)
    if is_room_thread(thread):
        row = membership(int(thread['id']), uid)
        return bool(row and row.get('status') == 'member')
    if is_church_thread(thread):
        starter = int(thread.get('starter_id') or thread.get('user_low') or 0)
        if uid == starter:
            return True
        try:
            from app.models import church_community as cc
            return cc.can_edit_church_page(int(thread.get('campus_id') or 0))
        except Exception:
            return False
    return uid in (int(thread['user_low']), int(thread['user_high']))


def get_or_start_church_thread(user_id: int, campus_id: int = 0) -> int | None:
    uid = int(user_id)
    cid = int(campus_id or 0)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO dm_threads (user_low, user_high, thread_kind, campus_id, starter_id)
            VALUES (%s, 0, 'church', %s, %s)
            ON DUPLICATE KEY UPDATE starter_id = VALUES(starter_id)
            """,
            (uid, cid, uid),
        )
        db.commit()
    except Exception:
        try:
            cur.execute(
                "INSERT IGNORE INTO dm_threads (user_low, user_high) VALUES (%s, 0)",
                (uid,),
            )
            db.commit()
        except Exception:
            return None
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT id FROM dm_threads
            WHERE thread_kind='church' AND campus_id=%s AND user_low=%s AND user_high=0
            """,
            (cid, uid),
        )
        row = cur.fetchone()
        if row:
            return int(row['id'])
    except Exception:
        pass
    cur.execute("SELECT id FROM dm_threads WHERE user_low=%s AND user_high=0", (uid,))
    row = cur.fetchone()
    return int(row['id']) if row else None


def get_or_start_thread(a: int, b: int) -> int | None:
    if int(a) == int(b):
        return None
    low, high = (int(a), int(b)) if int(a) < int(b) else (int(b), int(a))
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT IGNORE INTO dm_threads (user_low, user_high) VALUES (%s,%s)", (low, high))
    db.commit()
    cur = _cur()
    cur.execute("SELECT id FROM dm_threads WHERE user_low=%s AND user_high=%s", (low, high))
    row = cur.fetchone()
    return int(row['id']) if row else None


def list_inbox(user_id: int) -> list[dict]:
    from app.models import church_community as cc

    uid = int(user_id)
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT t.*,
                   CASE WHEN t.user_low=%s THEN t.user_high ELSE t.user_low END AS other_id
            FROM dm_threads t
            WHERE t.user_low=%s OR t.user_high=%s
               OR (t.thread_kind='church' AND t.starter_id=%s)
               OR EXISTS (
                    SELECT 1 FROM dm_members m
                    WHERE m.thread_id=t.id AND m.user_id=%s AND m.status='member'
               )
            ORDER BY t.updated_at DESC
            """,
            (uid, uid, uid, uid, uid),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        try:
            cur.execute(
                """
                SELECT t.*,
                       CASE WHEN t.user_low=%s THEN t.user_high ELSE t.user_low END AS other_id
                FROM dm_threads t
                WHERE t.user_low=%s OR t.user_high=%s
                ORDER BY t.updated_at DESC
                """,
                (uid, uid, uid),
            )
            rows = list(cur.fetchall() or [])
        except Exception:
            return []
    seen = set()
    out = []
    church = cc.church_name()
    portrait_ids: list[int] = []
    for row in rows:
        tid = int(row.get('id') or 0)
        if tid in seen:
            continue
        if not user_can_use_thread(row, uid):
            continue
        seen.add(tid)
        if is_room_thread(row):
            row['is_church'] = False
            row['is_room'] = True
            row['is_open'] = (row.get('thread_kind') == 'open')
            row['other_name'] = (row.get('title') or '').strip() or ('Open note' if row['is_open'] else 'Group note')
            row['other_username'] = ''
            row['other_id'] = 0
            row['kicker'] = 'Open note' if row['is_open'] else 'Group note'
            row['initials'] = _initials(row['other_name'])
            out.append(row)
            continue
        if is_church_thread(row):
            starter = int(row.get('starter_id') or row.get('user_low') or 0)
            if uid == starter:
                row['other_name'] = church
                row['other_username'] = ''
                row['other_id'] = 0
                row['kicker'] = 'Church office'
            else:
                cur.execute(
                    "SELECT username, first_name, last_name FROM users WHERE id=%s",
                    (starter,),
                )
                other = cur.fetchone() or {}
                name = _person_name(other)
                row['other_name'] = name
                row['other_username'] = other.get('username') or ''
                row['other_id'] = starter
                row['kicker'] = f'Writing {church}'
                portrait_ids.append(starter)
            row['is_church'] = True
            out.append(row)
            continue
        cur.execute(
            "SELECT username, first_name, last_name FROM users WHERE id=%s",
            (row['other_id'],),
        )
        other = cur.fetchone() or {}
        row['other_name'] = _person_name(other)
        row['other_username'] = other.get('username') or ''
        row['is_church'] = False
        row['kicker'] = 'Member'
        if row.get('other_id'):
            portrait_ids.append(int(row['other_id']))
        out.append(row)

    last_by = _last_messages([int(r['id']) for r in out])
    pics = _member_portraits(portrait_ids)
    church_pic = church_portrait_url(0)
    for row in out:
        tid = int(row['id'])
        last = last_by.get(tid) or {}
        row['preview'] = last.get('preview') or 'No notes yet'
        row['preview_from_me'] = int(last.get('sender_id') or 0) == uid
        last_at = last.get('created_at') or row.get('updated_at')
        row['when_label'] = when_label(last_at)
        read_at = thread_read_at(row, uid)
        last_dt = _parse_dt(last.get('created_at'))
        read_dt = _parse_dt(read_at)
        row['unread'] = bool(
            last
            and int(last.get('sender_id') or 0) != uid
            and (read_dt is None or (last_dt and last_dt > read_dt))
        )
        row['initials'] = row.get('initials') or _initials(row.get('other_name') or '')
        if row.get('is_room'):
            row['pic_url'] = ''
            row['other_page_url'] = ''
        elif row.get('is_church') and not row.get('other_username'):
            row['pic_url'] = church_pic
            row['other_page_url'] = url_for('church.church_home')
        else:
            row['pic_url'] = pics.get(int(row.get('other_id') or 0), '')
            username = row.get('other_username') or ''
            row['other_page_url'] = url_for('church.member_page', username=username) if username else ''
    return out


def inbox_unread_count(user_id: int | None) -> int:
    if not user_id:
        return 0
    try:
        n = sum(1 for row in list_inbox(int(user_id)) if row.get('unread'))
        n += len(list_invites(int(user_id)))
        return n
    except Exception:
        return 0


def get_thread(thread_id: int, user_id: int) -> dict | None:
    cur = _cur()
    cur.execute("SELECT * FROM dm_threads WHERE id=%s", (int(thread_id),))
    row = cur.fetchone()
    if not row:
        return None
    if not user_can_use_thread(row, user_id):
        return None
    return row


def list_thread_messages(thread_id: int, viewer_id: int | None = None) -> list[dict]:
    from app.utils.dm_crypto import decrypt_dm

    cur = _cur()
    try:
        cur.execute(
            """
            SELECT m.id, m.thread_id, m.sender_id, m.body_enc, m.created_at,
                   u.username, u.first_name, u.last_name, s.photo_path
            FROM dm_messages m
            LEFT JOIN users u ON u.id = m.sender_id
            LEFT JOIN member_spaces s ON s.user_id = m.sender_id
            WHERE m.thread_id=%s
            ORDER BY m.id ASC
            """,
            (int(thread_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        cur.execute(
            """
            SELECT m.id, m.thread_id, m.sender_id, m.body_enc, m.created_at,
                   u.username, u.first_name, u.last_name
            FROM dm_messages m
            LEFT JOIN users u ON u.id = m.sender_id
            WHERE m.thread_id=%s
            ORDER BY m.id ASC
            """,
            (int(thread_id),),
        )
        rows = list(cur.fetchall() or [])
    vid = int(viewer_id) if viewer_id else 0
    for row in rows:
        row['body'] = decrypt_dm(row.get('body_enc') or '')
        row.pop('body_enc', None)
        row['display_name'] = _person_name(row)
        row['initials'] = _initials(row['display_name'])
        row['pic_url'] = identity_url(row.get('photo_path'))
        row['when_label'] = message_when(row.get('created_at'))
        row['is_mine'] = bool(vid and int(row.get('sender_id') or 0) == vid)
    return rows


def send_message(thread_id: int, sender_id: int, body: str) -> tuple[bool, str]:
    from app.utils.dm_crypto import encrypt_dm

    text = sanitize_plain_text(body)
    if not text:
        return False, 'Say something first — even a short hello.'
    if len(text) > MAX_MESSAGE_LEN:
        return False, 'That note is too long. Keep it under 4,000 characters.'
    if contains_censored_word(text):
        return False, 'That wording isn’t allowed here. Try saying it another way.'
    if hour_message_count(sender_id) >= 30:
        return False, 'Slow down a little — 30 notes an hour is the limit.'
    thread = get_thread(thread_id, sender_id)
    if not thread:
        return False, 'That conversation isn’t here.'
    if not is_church_thread(thread) and not is_room_thread(thread):
        other = thread['user_high'] if int(thread['user_low']) == int(sender_id) else thread['user_low']
        if blocked_either_way(sender_id, other):
            return False, 'That page does not exist.'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO dm_messages (thread_id, sender_id, body_enc) VALUES (%s,%s,%s)",
        (int(thread_id), int(sender_id), encrypt_dm(text)),
    )
    cur.execute("UPDATE dm_threads SET updated_at=NOW() WHERE id=%s", (int(thread_id),))
    db.commit()
    try:
        from app.utils.note_notify import notify_note_reply
        sender = {}
        try:
            cur = _cur()
            cur.execute("SELECT first_name, last_name, username FROM users WHERE id=%s", (int(sender_id),))
            sender = cur.fetchone() or {}
        except Exception:
            sender = {}
        notify_note_reply(thread, int(sender_id), _person_name(sender))
    except Exception as exc:
        print(f'note notify skipped: {exc}')
    return True, ''


def mark_thread_read(thread_id: int, user_id: int) -> None:
    thread = get_thread(thread_id, user_id)
    if not thread:
        return
    uid = int(user_id)
    if is_room_thread(thread):
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                "UPDATE dm_members SET last_read_at=NOW() WHERE thread_id=%s AND user_id=%s",
                (int(thread_id), uid),
            )
            db.commit()
        except Exception:
            db.rollback()
        return
    if is_church_thread(thread):
        starter = int(thread.get('starter_id') or thread.get('user_low') or 0)
        col = 'last_read_at_low' if uid == starter else 'last_read_at_high'
    else:
        col = 'last_read_at_low' if uid == int(thread['user_low']) else 'last_read_at_high'
    db = get_db()
    cur = db.cursor()
    cur.execute(f"UPDATE dm_threads SET {col}=NOW() WHERE id=%s", (int(thread_id),))
    db.commit()


MAX_ROOM_MEMBERS = 40


def _add_member(thread_id: int, user_id: int, status: str, role: str = 'member', notify_email: int = 0) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO dm_members (thread_id, user_id, status, role, notify_email)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status=VALUES(status),
            role=IF(role='owner', role, VALUES(role)),
            notify_email=VALUES(notify_email)
        """,
        (int(thread_id), int(user_id), status, role, int(notify_email)),
    )
    db.commit()


def room_member_count(thread_id: int) -> int:
    cur = _cur()
    try:
        cur.execute(
            "SELECT COUNT(*) AS n FROM dm_members WHERE thread_id=%s AND status='member'",
            (int(thread_id),),
        )
        return int((cur.fetchone() or {}).get('n') or 0)
    except Exception:
        return 0


def list_room_members(thread_id: int) -> list[dict]:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT m.*, u.username, u.first_name, u.last_name
            FROM dm_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.thread_id=%s
            ORDER BY m.role='owner' DESC, m.status='member' DESC, u.first_name ASC
            """,
            (int(thread_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    out = []
    for row in rows:
        name = _person_name(row)
        out.append({
            **row,
            'display_name': name,
            'initials': _initials(name),
        })
    return out


def create_room(owner_id: int, title: str, open_join: bool, invite_ids: list[int] | None = None) -> tuple[int | None, str]:
    import random
    name = sanitize_plain_text(title)[:160]
    if not name:
        return None, 'Give this note a name.'
    if contains_censored_word(name):
        return None, 'That name isn’t allowed.'
    kind = 'open' if open_join else 'group'
    policy = 'open' if open_join else 'invite'
    db = get_db()
    cur = db.cursor()
    tid = None
    for _ in range(5):
        nonce = random.randint(1, 2_000_000_000)
        try:
            cur.execute(
                """
                INSERT INTO dm_threads (user_low, user_high, thread_kind, campus_id, title, created_by, join_policy)
                VALUES (%s, %s, %s, 0, %s, %s, %s)
                """,
                (int(owner_id), nonce, kind, name, int(owner_id), policy),
            )
            db.commit()
            tid = int(cur.lastrowid)
            break
        except Exception:
            db.rollback()
    if not tid:
        return None, 'Could not start that note.'
    _add_member(tid, owner_id, 'member', role='owner', notify_email=0)
    invited = 0
    for raw in invite_ids or []:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid == int(owner_id):
            continue
        if blocked_either_way(owner_id, uid):
            continue
        if room_member_count(tid) + invited >= MAX_ROOM_MEMBERS:
            break
        _add_member(tid, uid, 'invited', role='member')
        invited += 1
    return tid, ''


def invite_to_room(thread_id: int, actor_id: int, user_id: int) -> tuple[bool, str]:
    thread = get_thread(thread_id, actor_id)
    if not thread or not is_room_thread(thread):
        return False, 'That note isn’t here.'
    mine = membership(thread_id, actor_id) or {}
    if mine.get('status') != 'member':
        return False, 'You are not in that note.'
    uid = int(user_id)
    if uid == int(actor_id):
        return False, 'You are already in it.'
    if blocked_either_way(actor_id, uid):
        return False, 'That page does not exist.'
    existing = membership(thread_id, uid)
    if existing and existing.get('status') == 'member':
        return False, 'They are already in this note.'
    if room_member_count(thread_id) >= MAX_ROOM_MEMBERS:
        return False, 'This note is full.'
    _add_member(thread_id, uid, 'invited' if thread.get('thread_kind') == 'group' else 'member')
    if thread.get('thread_kind') == 'open':
        return True, 'They are in the open note.'
    return True, 'Invite sent — they have to accept.'


def accept_invite(thread_id: int, user_id: int) -> tuple[bool, str]:
    row = membership(thread_id, user_id)
    if not row or row.get('status') not in ('invited', 'left', 'declined'):
        return False, 'That invite is not waiting.'
    if room_member_count(thread_id) >= MAX_ROOM_MEMBERS:
        return False, 'This note is full.'
    _add_member(thread_id, user_id, 'member', role=row.get('role') or 'member')
    return True, 'You joined the note.'


def decline_invite(thread_id: int, user_id: int) -> tuple[bool, str]:
    row = membership(thread_id, user_id)
    if not row or row.get('status') != 'invited':
        return False, 'That invite is not waiting.'
    _add_member(thread_id, user_id, 'declined', role=row.get('role') or 'member')
    return True, 'Invite declined.'


def join_open_room(thread_id: int, user_id: int) -> tuple[bool, str]:
    cur = _cur()
    cur.execute("SELECT * FROM dm_threads WHERE id=%s", (int(thread_id),))
    thread = cur.fetchone()
    if not thread or thread.get('thread_kind') != 'open':
        return False, 'That open note isn’t here.'
    existing = membership(thread_id, user_id)
    if existing and existing.get('status') == 'member':
        return True, 'You are already in it.'
    if room_member_count(thread_id) >= MAX_ROOM_MEMBERS:
        return False, 'This note is full.'
    _add_member(thread_id, user_id, 'member')
    return True, 'You joined the open note.'


def leave_room(thread_id: int, user_id: int) -> tuple[bool, str]:
    row = membership(thread_id, user_id)
    if not row or row.get('status') != 'member':
        return False, 'You are not in that note.'
    db = get_db()
    cur = db.cursor()
    if row.get('role') == 'owner':
        cur.execute(
            """
            SELECT user_id FROM dm_members
            WHERE thread_id=%s AND status='member' AND user_id != %s
            ORDER BY joined_at ASC LIMIT 1
            """,
            (int(thread_id), int(user_id)),
        )
        nxt = cur.fetchone()
        if nxt:
            cur.execute(
                "UPDATE dm_members SET role='owner' WHERE thread_id=%s AND user_id=%s",
                (int(thread_id), int(nxt['user_id'])),
            )
    cur.execute(
        "UPDATE dm_members SET status='left', role='member' WHERE thread_id=%s AND user_id=%s",
        (int(thread_id), int(user_id)),
    )
    db.commit()
    return True, 'You left the note.'


def set_room_notify(thread_id: int, user_id: int, email: bool | None = None, push: bool | None = None) -> None:
    row = membership(thread_id, user_id)
    if not row:
        return
    db = get_db()
    cur = db.cursor()
    if email is not None:
        cur.execute(
            "UPDATE dm_members SET notify_email=%s WHERE thread_id=%s AND user_id=%s",
            (1 if email else 0, int(thread_id), int(user_id)),
        )
    if push is not None:
        cur.execute(
            "UPDATE dm_members SET notify_push=%s WHERE thread_id=%s AND user_id=%s",
            (1 if push else 0, int(thread_id), int(user_id)),
        )
    db.commit()


def list_invites(user_id: int) -> list[dict]:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT t.id, t.title, t.thread_kind, t.updated_at, t.created_by,
                   u.username AS host_username, u.first_name, u.last_name
            FROM dm_members m
            JOIN dm_threads t ON t.id = m.thread_id
            LEFT JOIN users u ON u.id = t.created_by
            WHERE m.user_id=%s AND m.status='invited'
            ORDER BY t.updated_at DESC
            """,
            (int(user_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    out = []
    for row in rows:
        host = _person_name(row)
        title = (row.get('title') or '').strip() or 'Group note'
        out.append({
            **row,
            'title': title,
            'host_name': host or 'A member',
            'when_label': when_label(row.get('updated_at')),
        })
    return out


def list_open_rooms(user_id: int) -> list[dict]:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT t.id, t.title, t.updated_at, t.created_by,
                   (SELECT COUNT(*) FROM dm_members m2 WHERE m2.thread_id=t.id AND m2.status='member') AS members
            FROM dm_threads t
            WHERE t.thread_kind='open'
              AND NOT EXISTS (
                  SELECT 1 FROM dm_members m
                  WHERE m.thread_id=t.id AND m.user_id=%s AND m.status='member'
              )
            ORDER BY t.updated_at DESC
            LIMIT 24
            """,
            (int(user_id),),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    out = []
    for row in rows:
        out.append({
            **row,
            'title': (row.get('title') or '').strip() or 'Open note',
            'when_label': when_label(row.get('updated_at')),
        })
    return out


def worship_lineup(campus_id: int | None = None, date_str: str | None = None) -> dict | None:
    try:
        from app.models.worship.setlists import get_upcoming_setlist, plan_is_active_schedule
        from app.models.worship import templates as tmpl

        row = None
        if date_str:
            row = tmpl.get_setlist_for_date(str(date_str)[:10])
            if not plan_is_active_schedule(row):
                row = None
        if not row:
            row = get_upcoming_setlist()
        if not row:
            return None
        songs = []
        for item in (row.get('songs') or [])[:8]:
            if isinstance(item, dict):
                songs.append(item.get('title') or item.get('name') or item.get('song_title') or '')
            elif item:
                songs.append(str(item))
        return {
            'title': row.get('title') or row.get('service_title') or 'Worship',
            'service_date': row.get('service_date'),
            'songs': [s for s in songs if s],
        }
    except Exception:
        return None
