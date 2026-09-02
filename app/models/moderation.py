# Reversible site-moderation ledger.
# Mods hide / shadow / warn / remove. Reviewers (or Admin/Owner) can put it back.

from __future__ import annotations

import json
from typing import Any

import pymysql

from app.models.db import get_db


ACTION_LABELS = {
    'comment_remove': 'Removed a comment',
    'comment_shadow': 'Shadowed a comment',
    'comment_unshadow': 'Unshadowed a comment',
    'comment_edit': 'Edited a comment',
    'post_hide': 'Hid a wall post',
    'post_shadow': 'Shadowed a wall post',
    'post_restore': 'Restored a wall post',
    'user_warn': 'Warned a member',
    'user_shadow': 'Shadowed an account',
    'user_unshadow': 'Removed a shadow ban',
    'user_ban': 'Banned an account',
    'user_unban': 'Unbanned an account',
    'user_lock': 'Locked login',
    'user_unlock': 'Unlocked login',
}

REVERSIBLE = frozenset({
    'comment_remove', 'comment_shadow', 'comment_edit',
    'post_hide', 'post_shadow', 'user_warn', 'user_shadow', 'user_ban', 'user_lock',
})


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def ensure_tables() -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS moderation_actions (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            actor_id INT UNSIGNED NOT NULL,
            action_type VARCHAR(40) NOT NULL,
            target_kind VARCHAR(40) NOT NULL,
            target_table VARCHAR(64) NULL,
            target_id INT UNSIGNED NULL,
            target_user_id INT UNSIGNED NULL,
            reason VARCHAR(500) NULL,
            snapshot_json MEDIUMTEXT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            reversed_by INT UNSIGNED NULL,
            reversed_at DATETIME NULL,
            reverse_note VARCHAR(500) NULL,
            reviewed_by INT UNSIGNED NULL,
            reviewed_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_mod_status (status, created_at),
            INDEX idx_mod_actor (actor_id, created_at),
            INDEX idx_mod_target (target_kind, target_id),
            INDEX idx_mod_user (target_user_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    db.commit()
    _ensure_comment_removed(cur)
    _ensure_post_removed(cur)
    db.commit()


def _ensure_comment_removed(cur) -> None:
    from app.builddb.comment_moderation import COMMENT_TABLES
    for table in COMMENT_TABLES:
        try:
            cur.execute(
                """
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'removed'
                """,
                (table,),
            )
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {table} ADD COLUMN removed TINYINT(1) NOT NULL DEFAULT 0")
        except Exception:
            pass


def _ensure_post_removed(cur) -> None:
    try:
        cur.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'community_posts'
              AND COLUMN_NAME = 'removed_at'
            """
        )
        if not cur.fetchone():
            cur.execute("ALTER TABLE community_posts ADD COLUMN removed_at DATETIME NULL")
            cur.execute("ALTER TABLE community_posts ADD COLUMN removed_by INT UNSIGNED NULL")
        cur.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'community_posts'
              AND COLUMN_NAME = 'shadowed'
            """
        )
        if not cur.fetchone():
            cur.execute("ALTER TABLE community_posts ADD COLUMN shadowed TINYINT(1) NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE community_posts ADD COLUMN shadowed_at DATETIME NULL")
            cur.execute("ALTER TABLE community_posts ADD COLUMN shadowed_by INT UNSIGNED NULL")
    except Exception:
        pass


def record_action(
    *,
    actor_id: int | None,
    action_type: str,
    target_kind: str,
    target_table: str | None = None,
    target_id: int | None = None,
    target_user_id: int | None = None,
    reason: str = '',
    snapshot: dict | None = None,
) -> int | None:
    if not actor_id:
        return None
    ensure_tables()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO moderation_actions
              (actor_id, action_type, target_kind, target_table, target_id, target_user_id,
               reason, snapshot_json, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
            """,
            (
                int(actor_id),
                action_type,
                target_kind,
                target_table,
                int(target_id) if target_id else None,
                int(target_user_id) if target_user_id else None,
                (reason or '')[:500] or None,
                json.dumps(snapshot or {}, default=str),
            ),
        )
        db.commit()
        return int(cur.lastrowid)
    except Exception as exc:
        print(f'moderation record: {exc}')
        try:
            db.rollback()
        except Exception:
            pass
        return None


def get_action(action_id: int) -> dict | None:
    ensure_tables()
    cur = _cur()
    cur.execute(
        """
        SELECT a.*,
               u.username AS actor_username,
               TRIM(CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,''))) AS actor_name,
               t.username AS target_username
        FROM moderation_actions a
        LEFT JOIN users u ON u.id = a.actor_id
        LEFT JOIN users t ON t.id = a.target_user_id
        WHERE a.id = %s
        LIMIT 1
        """,
        (int(action_id),),
    )
    row = cur.fetchone()
    return _decorate(row) if row else None


def list_actions(*, status: str = 'active', limit: int = 80, actor_id: int | None = None) -> list[dict]:
    ensure_tables()
    cur = _cur()
    where = []
    args: list[Any] = []
    if status and status != 'all':
        where.append('a.status = %s')
        args.append(status)
    if actor_id:
        where.append('a.actor_id = %s')
        args.append(int(actor_id))
    sql = """
        SELECT a.*,
               u.username AS actor_username,
               TRIM(CONCAT(COALESCE(u.first_name,''),' ',COALESCE(u.last_name,''))) AS actor_name,
               t.username AS target_username
        FROM moderation_actions a
        LEFT JOIN users u ON u.id = a.actor_id
        LEFT JOIN users t ON t.id = a.target_user_id
    """
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY a.created_at DESC LIMIT %s'
    args.append(int(limit))
    cur.execute(sql, args)
    return [_decorate(r) for r in (cur.fetchall() or [])]


def active_warnings_for(user_id: int) -> list[dict]:
    if not user_id:
        return []
    ensure_tables()
    cur = _cur()
    cur.execute(
        """
        SELECT * FROM moderation_actions
        WHERE target_user_id = %s AND action_type = 'user_warn' AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 8
        """,
        (int(user_id),),
    )
    return [_decorate(r) for r in (cur.fetchall() or [])]


def _decorate(row: dict) -> dict:
    snap = {}
    try:
        snap = json.loads(row.get('snapshot_json') or '{}') or {}
    except (TypeError, json.JSONDecodeError):
        snap = {}
    row['snapshot'] = snap
    row['label'] = ACTION_LABELS.get(row.get('action_type') or '', row.get('action_type') or 'Action')
    row['can_reverse'] = (row.get('status') == 'active') and (row.get('action_type') in REVERSIBLE)
    preview = snap.get('body') or snap.get('title') or snap.get('message') or snap.get('old_body') or ''
    row['preview'] = (preview or '')[:280]
    return row


def mark_status(action_id: int, status: str, *, by: int, note: str = '') -> None:
    db = get_db()
    cur = db.cursor()
    if status == 'reversed':
        cur.execute(
            """
            UPDATE moderation_actions
            SET status='reversed', reversed_by=%s, reversed_at=NOW(), reverse_note=%s
            WHERE id=%s AND status='active'
            """,
            (int(by), (note or '')[:500] or None, int(action_id)),
        )
    elif status == 'upheld':
        cur.execute(
            """
            UPDATE moderation_actions
            SET status='upheld', reviewed_by=%s, reviewed_at=NOW()
            WHERE id=%s AND status='active'
            """,
            (int(by), int(action_id)),
        )
    db.commit()


def reverse_action(action_id: int, reviewer_id: int, note: str = '') -> str:
    """Undo a recorded action. Returns a short status message."""
    row = get_action(action_id)
    if not row:
        raise ValueError('That moderation record is gone.')
    if row.get('status') != 'active':
        raise ValueError('That action was already reviewed or reversed.')
    kind = row.get('action_type') or ''
    if kind not in REVERSIBLE:
        raise ValueError('That action is not reversible from here.')
    snap = row.get('snapshot') or {}
    _apply_reverse(kind, row, snap, reviewer_id)
    mark_status(action_id, 'reversed', by=reviewer_id, note=note)
    return 'Reversed. The original is back.'


def uphold_action(action_id: int, reviewer_id: int) -> str:
    row = get_action(action_id)
    if not row:
        raise ValueError('That moderation record is gone.')
    if row.get('status') != 'active':
        raise ValueError('Already reviewed.')
    mark_status(action_id, 'upheld', by=reviewer_id)
    return 'Marked as looks good.'


def _apply_reverse(kind: str, row: dict, snap: dict, reviewer_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    table = row.get('target_table') or snap.get('table')
    tid = row.get('target_id') or snap.get('id')
    uid = row.get('target_user_id')

    if kind == 'comment_remove' and table and tid:
        cur.execute(f"UPDATE {table} SET removed=0 WHERE id=%s", (int(tid),))
        db.commit()
        return
    if kind == 'comment_shadow' and table and tid:
        cur.execute(
            f"""
            UPDATE {table}
            SET shadowed=0, shadow_ip=NULL, shadow_user_id=NULL
            WHERE id=%s
            """,
            (int(tid),),
        )
        db.commit()
        return
    if kind == 'comment_edit' and table and tid and snap.get('old_body') is not None:
        from app.utils.comment_moderation import COMMENT_TYPES
        text_col = 'comment'
        for cfg in COMMENT_TYPES.values():
            if cfg['table'] == table:
                text_col = cfg['text_col']
                break
        cur.execute(
            f"UPDATE {table} SET {text_col}=%s WHERE id=%s",
            (snap.get('old_body'), int(tid)),
        )
        db.commit()
        return
    if kind == 'post_hide' and tid:
        cur.execute(
            "UPDATE community_posts SET removed_at=NULL, removed_by=NULL WHERE id=%s",
            (int(tid),),
        )
        db.commit()
        return
    if kind == 'post_shadow' and tid:
        cur.execute(
            "UPDATE community_posts SET shadowed=0, shadowed_at=NULL, shadowed_by=NULL WHERE id=%s",
            (int(tid),),
        )
        db.commit()
        return
    if kind == 'user_shadow' and uid:
        from app.models.users import set_shadow_ban
        set_shadow_ban(int(uid), False, int(reviewer_id), record=False)
        return
    if kind == 'user_warn':
        return
    if kind == 'user_ban' and uid:
        from app.models.users import unban_user
        prev = snap.get('previous_role') or 'Member'
        if prev == 'banned':
            prev = 'Member'
        unban_user(int(uid), int(reviewer_id), role=prev, record=False)
        return
    if kind == 'user_lock' and uid:
        from app.models.users import clear_account_login_lock
        clear_account_login_lock(int(uid), int(reviewer_id), record=False)
        return
    raise ValueError('Could not reverse that action.')


def hide_post(post_id: int, actor_id: int, reason: str = '') -> tuple[bool, str]:
    from app.models.social import get_community_post
    ensure_tables()
    row = get_community_post(post_id)
    if not row:
        return False, 'That post is gone.'
    if row.get('removed_at'):
        return False, 'That post is already hidden.'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE community_posts SET removed_at=NOW(), removed_by=%s WHERE id=%s",
        (int(actor_id), int(post_id)),
    )
    db.commit()
    record_action(
        actor_id=actor_id,
        action_type='post_hide',
        target_kind='post',
        target_table='community_posts',
        target_id=int(post_id),
        target_user_id=row.get('user_id'),
        reason=reason,
        snapshot={
            'title': row.get('title'),
            'body': row.get('body'),
            'kind': row.get('kind'),
            'visibility': row.get('visibility'),
        },
    )
    if reason and row.get('user_id'):
        try:
            warn_user(int(row['user_id']), actor_id, reason)
        except Exception:
            pass
    return True, 'Post removed. A reviewer can put it back.'


def shadow_post(post_id: int, actor_id: int, reason: str = '') -> tuple[bool, str]:
    from app.models.social import get_community_post
    ensure_tables()
    row = get_community_post(post_id)
    if not row:
        return False, 'That post is gone.'
    if row.get('removed_at'):
        return False, 'That post was already removed.'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE community_posts
        SET shadowed=1, shadowed_at=NOW(), shadowed_by=%s
        WHERE id=%s
        """,
        (int(actor_id), int(post_id)),
    )
    db.commit()
    record_action(
        actor_id=actor_id,
        action_type='post_shadow',
        target_kind='post',
        target_table='community_posts',
        target_id=int(post_id),
        target_user_id=row.get('user_id'),
        reason=reason,
        snapshot={
            'title': row.get('title'),
            'body': row.get('body'),
            'kind': row.get('kind'),
            'visibility': row.get('visibility'),
        },
    )
    return True, 'Shadowed — only they still see it. A reviewer can reverse this.'


def unshadow_post(post_id: int, actor_id: int) -> tuple[bool, str]:
    from app.models.social import get_community_post
    ensure_tables()
    row = get_community_post(post_id)
    if not row:
        return False, 'That post is gone.'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE community_posts SET shadowed=0, shadowed_at=NULL, shadowed_by=NULL WHERE id=%s",
        (int(post_id),),
    )
    db.commit()
    record_action(
        actor_id=actor_id,
        action_type='post_restore',
        target_kind='post',
        target_table='community_posts',
        target_id=int(post_id),
        target_user_id=row.get('user_id'),
    )
    return True, 'Everyone can see that post again.'


def warn_user(user_id: int, actor_id: int, message: str) -> None:
    message = (message or '').strip()
    if not message:
        raise ValueError('Write a short warning note.')
    record_action(
        actor_id=actor_id,
        action_type='user_warn',
        target_kind='user',
        target_table='users',
        target_id=int(user_id),
        target_user_id=int(user_id),
        reason=message,
        snapshot={'message': message},
    )


def can_moderate_site() -> bool:
    from app.utils.permissions import user_has_permission
    return bool(user_has_permission('moderate_site'))


def can_moderate_walls() -> bool:
    """Site mods, Owner/Admin, or church-page editors (not posters)."""
    from flask import has_request_context, session
    from app.utils.permissions import user_has_permission
    if user_has_permission('moderate_site'):
        return True
    if not has_request_context():
        return False
    if (session.get('user_role') or '') in ('Owner', 'Admin'):
        return True
    uid = session.get('user_id')
    if not uid:
        return False
    try:
        from app.models import church_community as cc
        if cc.can_edit_church_page(0):
            return True
        cur = _cur()
        cur.execute(
            """
            SELECT 1 FROM church_page_editors
            WHERE user_id=%s AND editor_role IN ('editor','admin')
            LIMIT 1
            """,
            (int(uid),),
        )
        return bool(cur.fetchone())
    except Exception:
        return False


def flag_wall_moderation(items: list[dict] | None) -> list[dict]:
    """Mark compose/wall posts that a church admin or site mod can act on."""
    from app.models.social import WALL_POST_KINDS
    can = can_moderate_walls()
    kinds = set(WALL_POST_KINDS)
    for item in items or []:
        kind = (item.get('type') or item.get('kind') or '').strip()
        item['moderatable'] = bool(can and item.get('id') and kind in kinds)
        item['shadowed_badge'] = bool(can and item.get('shadowed'))
    return items or []


def can_review_moderation() -> bool:
    from app.utils.permissions import user_has_permission
    return bool(user_has_permission('review_moderation'))
