# Reactions, comments, and reshares on feed / wall posts.

from __future__ import annotations

from flask import url_for

from app.models.db import get_db

REACTIONS = (
    ('like', 'Like', 'fa-solid fa-thumbs-up'),
    ('love', 'Love', 'fa-solid fa-heart'),
    ('pray', 'Praying', 'fa-solid fa-hands-praying'),
    ('amen', 'Amen', 'fa-solid fa-hands'),
    ('disagree', 'Disagree', 'fa-solid fa-thumbs-down'),
    ('sad', 'Sad', 'fa-solid fa-face-sad-tear'),
    ('mad', 'Mad', 'fa-solid fa-face-angry'),
)
REACTION_KEYS = {k for k, _n, _i in REACTIONS}
WALL_KINDS = ('post', 'quote', 'verse', 'image', 'book', 'blog', 'share')


def _cur():
    import pymysql
    return get_db().cursor(pymysql.cursors.DictCursor)


def set_reaction(content_type: str, content_id: int, user_id: int, reaction: str) -> tuple[bool, str]:
    kind = (content_type or 'post').strip().lower()
    react = (reaction or '').strip().lower()
    if react and react not in REACTION_KEYS:
        return False, 'Unknown reaction.'
    db = get_db()
    cur = db.cursor()
    if not react:
        cur.execute(
            "DELETE FROM content_reactions WHERE content_type=%s AND content_id=%s AND user_id=%s",
            (kind, int(content_id), int(user_id)),
        )
        db.commit()
        return True, 'Reaction removed.'
    try:
        cur.execute(
            """
            INSERT INTO content_reactions (content_type, content_id, user_id, reaction)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE reaction = VALUES(reaction)
            """,
            (kind, int(content_id), int(user_id), react),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        return False, str(exc)
    return True, 'Reacted.'


def reshare(content_type: str, content_id: int, user_id: int) -> tuple[bool, str]:
    kind = (content_type or 'post').strip().lower()
    from app.models import social as social_model
    if kind in WALL_KINDS:
        src = social_model.get_community_post(int(content_id))
        if not src:
            return False, 'That post is gone.'
        if src.get('allow_share') in (0, '0', False):
            return False, 'They turned off resharing on this post.'
        if int(src.get('user_id') or 0) == int(user_id):
            return False, 'That’s already on your page.'
        title = (src.get('title') or 'Post')[:200]
        body = (src.get('body') or '')[:500]
        new_id = social_model.create_post(
            int(user_id),
            'share',
            f"Shared: {title}",
            body,
            src.get('url') or '',
            'public',
            image_path=src.get('image_path'),
            allow_comments=True,
            allow_share=True,
            share_of=int(content_id),
        )
        if not new_id:
            return False, 'Could not reshare that.'
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT IGNORE INTO content_shares (content_type, content_id, user_id)
            VALUES (%s, %s, %s)
            """,
            (kind, int(content_id), int(user_id)),
        )
        db.commit()
    except Exception:
        db.rollback()
    return True, 'Shared to your page.'


def attach_social(items: list[dict], viewer_id: int | None = None) -> list[dict]:
    if not items:
        return items
    pairs = []
    for item in items:
        kind = (item.get('type') or '').strip()
        try:
            oid = int(item.get('id') or 0)
        except (TypeError, ValueError):
            oid = 0
        if kind and oid:
            pairs.append((kind, oid))
    counts: dict[tuple, dict] = {}
    mine: dict[tuple, str] = {}
    shares: dict[tuple, int] = {}
    if pairs:
        try:
            cur = _cur()
            ph = ','.join(['(%s,%s)'] * len(pairs))
            flat = [x for p in pairs for x in p]
            cur.execute(
                f"""
                SELECT content_type, content_id, reaction, COUNT(*) AS n
                FROM content_reactions
                WHERE (content_type, content_id) IN ({ph})
                GROUP BY content_type, content_id, reaction
                """,
                flat,
            )
            for row in cur.fetchall() or []:
                key = ((row.get('content_type') or ''), int(row.get('content_id') or 0))
                counts.setdefault(key, {})[row.get('reaction') or 'like'] = int(row.get('n') or 0)
            if viewer_id:
                cur.execute(
                    f"""
                    SELECT content_type, content_id, reaction
                    FROM content_reactions
                    WHERE user_id=%s AND (content_type, content_id) IN ({ph})
                    """,
                    (int(viewer_id), *flat),
                )
                for row in cur.fetchall() or []:
                    key = ((row.get('content_type') or ''), int(row.get('content_id') or 0))
                    mine[key] = row.get('reaction') or ''
            cur.execute(
                f"""
                SELECT content_type, content_id, COUNT(*) AS n
                FROM content_shares
                WHERE (content_type, content_id) IN ({ph})
                GROUP BY content_type, content_id
                """,
                flat,
            )
            for row in cur.fetchall() or []:
                key = ((row.get('content_type') or ''), int(row.get('content_id') or 0))
                shares[key] = int(row.get('n') or 0)
        except Exception as exc:
            print(f'attach_social: {exc}')
    originals: dict[int, dict] = {}
    share_ids = [int(i.get('share_of') or 0) for i in items if i.get('share_of')]
    share_ids = [s for s in share_ids if s]
    if share_ids:
        try:
            from app.models import social as social_model
            cur = _cur()
            ph = ','.join(['%s'] * len(share_ids))
            cur.execute(
                f"""
                SELECT p.*, u.username, u.first_name, u.last_name
                FROM community_posts p
                LEFT JOIN users u ON u.id = p.user_id
                WHERE p.id IN ({ph})
                """,
                share_ids,
            )
            for row in cur.fetchall() or []:
                originals[int(row['id'])] = social_model._decorate_post_row(dict(row))
        except Exception:
            originals = {}
    from app.routes.public.public_dashboard.queries import get_recent_comments
    for item in items:
        kind = (item.get('type') or '').strip()
        try:
            oid = int(item.get('id') or 0)
        except (TypeError, ValueError):
            oid = 0
        key = (kind, oid)
        item['reactions'] = counts.get(key) or {}
        item['reaction_total'] = sum(item['reactions'].values())
        item['my_reaction'] = mine.get(key) or ''
        item['share_count'] = shares.get(key) or 0
        if 'allow_comments' not in item or item.get('allow_comments') is None:
            item['allow_comments'] = True
        if 'allow_share' not in item or item.get('allow_share') is None:
            item['allow_share'] = True
        if oid and kind in WALL_KINDS and not item.get('comments'):
            try:
                item['comments'] = get_recent_comments(kind, oid, limit=4)
            except Exception:
                item['comments'] = item.get('comments') or []
        so = int(item.get('share_of') or 0)
        if so and originals.get(so):
            item['shared_from'] = originals[so]
            try:
                item['shared_from']['page_url'] = url_for(
                    'church.member_page', username=originals[so].get('username') or '',
                ) if originals[so].get('username') else ''
            except Exception:
                item['shared_from']['page_url'] = ''
    return items
