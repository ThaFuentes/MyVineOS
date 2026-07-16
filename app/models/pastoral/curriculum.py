# Curriculum data access — series, lessons, interactive blocks, learner progress.

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Optional

import pymysql
from werkzeug.utils import secure_filename

from app.models.db import get_db

BLOCK_TYPES = (
    'text',
    'scripture',
    'image',
    'video',
    'multiple_choice',
    'true_false',
    'fill_blank',
    'divider',
)

AUDIENCES = (
    ('everyone', 'Everyone'),
    ('adults', 'Adults'),
    ('youth', 'Youth'),
    ('kids', 'Kids / Children'),
    ('leaders', 'Leaders & Ministers'),
    ('new_believers', 'New Believers'),
)

STATUSES = ('draft', 'published', 'archived')

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
VIDEO_EXTS = {'.mp4', '.webm', '.mov'}


def _cursor():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _scalar(row, default=0):
    """First column value from a fetchone() row (DictCursor or tuple)."""
    if row is None:
        return default
    if isinstance(row, dict):
        if not row:
            return default
        return next(iter(row.values()))
    try:
        return row[0]
    except (IndexError, KeyError, TypeError):
        return default


def _loads(raw, default=None):
    if raw is None or raw == '':
        return default if default is not None else []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else []


def _dumps(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


# ── Series ──────────────────────────────────────────────────────────────────

def list_series(
    *,
    status: str | None = None,
    audience: str | None = None,
    search: str | None = None,
    for_learners: bool = False,
    limit: int = 200,
) -> list[dict]:
    cur = _cursor()
    sql = """
        SELECT s.*,
               (SELECT COUNT(*) FROM curriculum_lessons l WHERE l.series_id = s.id) AS lesson_count,
               (SELECT COUNT(*) FROM curriculum_blocks b
                  JOIN curriculum_lessons l ON l.id = b.lesson_id
                 WHERE l.series_id = s.id) AS block_count
        FROM curriculum_series s
        WHERE 1=1
    """
    params: list[Any] = []
    if for_learners:
        sql += " AND s.status = 'published' AND s.visibility IN ('public','members')"
    elif status:
        sql += " AND s.status = %s"
        params.append(status)
    if audience:
        sql += " AND s.audience = %s"
        params.append(audience)
    if search:
        like = f"%{search}%"
        sql += " AND (s.title LIKE %s OR s.subtitle LIKE %s OR s.description LIKE %s OR s.tags LIKE %s)"
        params.extend([like, like, like, like])
    sql += " ORDER BY s.sort_order ASC, s.updated_at DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['tags_list'] = [t.strip() for t in (r.get('tags') or '').split(',') if t.strip()]
    return rows


def get_series(series_id: int) -> Optional[dict]:
    cur = _cursor()
    cur.execute("SELECT * FROM curriculum_series WHERE id = %s", (series_id,))
    row = cur.fetchone()
    if not row:
        return None
    row['tags_list'] = [t.strip() for t in (row.get('tags') or '').split(',') if t.strip()]
    return row


def create_series(data: dict, user_id: int | None) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO curriculum_series
            (title, subtitle, description, cover_image, audience, status, visibility,
             tags, estimated_minutes, sort_order, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            (data.get('title') or 'Untitled Course').strip()[:255],
            (data.get('subtitle') or '').strip()[:500] or None,
            (data.get('description') or '').strip() or None,
            data.get('cover_image') or None,
            data.get('audience') or 'everyone',
            data.get('status') or 'draft',
            data.get('visibility') or 'members',
            (data.get('tags') or '').strip()[:500] or None,
            int(data['estimated_minutes']) if data.get('estimated_minutes') else None,
            int(data.get('sort_order') or 0),
            user_id,
        ),
    )
    db.commit()
    return cur.lastrowid


def update_series(series_id: int, data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    fields = []
    vals = []
    mapping = {
        'title': lambda v: (v or '').strip()[:255],
        'subtitle': lambda v: (v or '').strip()[:500] or None,
        'description': lambda v: (v or '').strip() or None,
        'cover_image': lambda v: v or None,
        'audience': lambda v: v or 'everyone',
        'status': lambda v: v if v in STATUSES else 'draft',
        'visibility': lambda v: v or 'members',
        'tags': lambda v: (v or '').strip()[:500] or None,
        'estimated_minutes': lambda v: int(v) if v not in (None, '') else None,
        'sort_order': lambda v: int(v or 0),
    }
    for key, transform in mapping.items():
        if key in data:
            fields.append(f"{key} = %s")
            vals.append(transform(data[key]))
    if data.get('status') == 'published':
        fields.append("published_at = COALESCE(published_at, CURRENT_TIMESTAMP)")
    if not fields:
        return
    vals.append(series_id)
    cur.execute(f"UPDATE curriculum_series SET {', '.join(fields)} WHERE id = %s", vals)
    db.commit()


def delete_series(series_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM curriculum_series WHERE id = %s", (series_id,))
    db.commit()


def duplicate_series(series_id: int, user_id: int | None) -> int:
    src = get_series(series_id)
    if not src:
        raise ValueError('Series not found')
    new_id = create_series(
        {
            'title': f"{src['title']} (Copy)",
            'subtitle': src.get('subtitle'),
            'description': src.get('description'),
            'cover_image': src.get('cover_image'),
            'audience': src.get('audience'),
            'status': 'draft',
            'visibility': src.get('visibility') or 'members',
            'tags': src.get('tags'),
            'estimated_minutes': src.get('estimated_minutes'),
        },
        user_id,
    )
    for lesson in list_lessons(series_id):
        lid = create_lesson(
            new_id,
            {
                'title': lesson['title'],
                'summary': lesson.get('summary'),
                'status': 'draft',
                'estimated_minutes': lesson.get('estimated_minutes'),
                'sort_order': lesson.get('sort_order') or 0,
            },
        )
        for block in list_blocks(lesson['id']):
            new_block_id = create_block(
                lid,
                {
                    'block_type': block['block_type'],
                    'title': block.get('title'),
                    'body': block.get('body'),
                    'media_url': block.get('media_url'),
                    'media_path': block.get('media_path'),
                    'media_alt': block.get('media_alt'),
                    'question_prompt': block.get('question_prompt'),
                    'correct_answers': _loads(block.get('correct_answers_json'), []),
                    'explanation': block.get('explanation'),
                    'points': block.get('points') or 1,
                    'is_required': block.get('is_required', 1),
                    'sort_order': block.get('sort_order') or 0,
                    'settings': _loads(block.get('settings_json'), {}),
                },
            )
            for ch in list_choices(block['id']):
                add_choice(new_block_id, ch['label'], bool(ch.get('is_correct')), ch.get('sort_order') or 0)
    return new_id


# ── Lessons ─────────────────────────────────────────────────────────────────

def list_lessons(series_id: int, *, published_only: bool = False) -> list[dict]:
    cur = _cursor()
    sql = """
        SELECT l.*,
               (SELECT COUNT(*) FROM curriculum_blocks b WHERE b.lesson_id = l.id) AS block_count,
               (SELECT COUNT(*) FROM curriculum_blocks b
                 WHERE b.lesson_id = l.id
                   AND b.block_type IN ('multiple_choice','true_false','fill_blank')) AS question_count
        FROM curriculum_lessons l
        WHERE l.series_id = %s
    """
    params: list[Any] = [series_id]
    if published_only:
        sql += " AND l.status = 'published'"
    sql += " ORDER BY l.sort_order ASC, l.id ASC"
    cur.execute(sql, params)
    return list(cur.fetchall() or [])


def get_lesson(lesson_id: int) -> Optional[dict]:
    cur = _cursor()
    cur.execute("SELECT * FROM curriculum_lessons WHERE id = %s", (lesson_id,))
    return cur.fetchone()


def create_lesson(series_id: int, data: dict) -> int:
    db = get_db()
    cur = db.cursor()
    # Default sort to end
    sort = data.get('sort_order')
    if sort is None:
        c2 = db.cursor()
        c2.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS next_sort FROM curriculum_lessons WHERE series_id=%s",
            (series_id,),
        )
        sort = _scalar(c2.fetchone(), 1)
    cur.execute(
        """
        INSERT INTO curriculum_lessons
            (series_id, title, summary, status, estimated_minutes, sort_order)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            series_id,
            (data.get('title') or 'New Lesson').strip()[:255],
            (data.get('summary') or '').strip() or None,
            data.get('status') or 'draft',
            int(data['estimated_minutes']) if data.get('estimated_minutes') else None,
            int(sort),
        ),
    )
    db.commit()
    return cur.lastrowid


def update_lesson(lesson_id: int, data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    fields, vals = [], []
    for key in ('title', 'summary', 'status', 'estimated_minutes', 'sort_order'):
        if key not in data:
            continue
        val = data[key]
        if key == 'title':
            val = (val or 'Untitled').strip()[:255]
        elif key == 'summary':
            val = (val or '').strip() or None
        elif key in ('estimated_minutes', 'sort_order'):
            val = int(val) if val not in (None, '') else (0 if key == 'sort_order' else None)
        fields.append(f"{key} = %s")
        vals.append(val)
    if not fields:
        return
    vals.append(lesson_id)
    cur.execute(f"UPDATE curriculum_lessons SET {', '.join(fields)} WHERE id = %s", vals)
    db.commit()


def delete_lesson(lesson_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM curriculum_lessons WHERE id = %s", (lesson_id,))
    db.commit()


def reorder_lessons(series_id: int, ordered_ids: list[int]) -> None:
    db = get_db()
    cur = db.cursor()
    for i, lid in enumerate(ordered_ids):
        cur.execute(
            "UPDATE curriculum_lessons SET sort_order=%s WHERE id=%s AND series_id=%s",
            (i, lid, series_id),
        )
    db.commit()


# ── Blocks ──────────────────────────────────────────────────────────────────

def list_blocks(lesson_id: int) -> list[dict]:
    cur = _cursor()
    cur.execute(
        """
        SELECT * FROM curriculum_blocks
        WHERE lesson_id = %s
        ORDER BY sort_order ASC, id ASC
        """,
        (lesson_id,),
    )
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['correct_answers'] = _loads(r.get('correct_answers_json'), [])
        r['settings'] = _loads(r.get('settings_json'), {})
        if r.get('block_type') in ('multiple_choice', 'true_false'):
            r['choices'] = list_choices(r['id'])
        else:
            r['choices'] = []
    return rows


def get_block(block_id: int) -> Optional[dict]:
    cur = _cursor()
    cur.execute("SELECT * FROM curriculum_blocks WHERE id = %s", (block_id,))
    row = cur.fetchone()
    if not row:
        return None
    row['correct_answers'] = _loads(row.get('correct_answers_json'), [])
    row['settings'] = _loads(row.get('settings_json'), {})
    row['choices'] = list_choices(block_id)
    return row


def create_block(lesson_id: int, data: dict) -> int:
    db = get_db()
    cur = db.cursor()
    btype = data.get('block_type') or 'text'
    if btype not in BLOCK_TYPES:
        btype = 'text'
    sort = data.get('sort_order')
    if sort is None:
        c2 = db.cursor()
        c2.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 AS next_sort FROM curriculum_blocks WHERE lesson_id=%s",
            (lesson_id,),
        )
        sort = _scalar(c2.fetchone(), 1)
    cur.execute(
        """
        INSERT INTO curriculum_blocks
            (lesson_id, block_type, title, body, media_url, media_path, media_alt,
             question_prompt, correct_answers_json, explanation, points, is_required,
             sort_order, settings_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            lesson_id,
            btype,
            (data.get('title') or '').strip()[:255] or None,
            data.get('body'),
            (data.get('media_url') or '').strip()[:1000] or None,
            data.get('media_path'),
            (data.get('media_alt') or '').strip()[:255] or None,
            data.get('question_prompt'),
            _dumps(data.get('correct_answers') or data.get('correct_answers_json') or []),
            data.get('explanation'),
            int(data.get('points') or 1),
            1 if data.get('is_required', True) else 0,
            int(sort),
            _dumps(data.get('settings') or {}),
        ),
    )
    db.commit()
    block_id = cur.lastrowid

    # Seed default true/false choices
    if btype == 'true_false' and not data.get('choices'):
        add_choice(block_id, 'True', True, 0)
        add_choice(block_id, 'False', False, 1)
    elif data.get('choices'):
        for i, ch in enumerate(data['choices']):
            if isinstance(ch, dict):
                add_choice(block_id, ch.get('label') or '', bool(ch.get('is_correct')), i)
            else:
                add_choice(block_id, str(ch), False, i)
    return block_id


def update_block(block_id: int, data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    fields, vals = [], []
    simple = {
        'block_type': lambda v: v if v in BLOCK_TYPES else 'text',
        'title': lambda v: (v or '').strip()[:255] or None,
        'body': lambda v: v,
        'media_url': lambda v: (v or '').strip()[:1000] or None,
        'media_path': lambda v: v or None,
        'media_alt': lambda v: (v or '').strip()[:255] or None,
        'question_prompt': lambda v: v,
        'explanation': lambda v: v,
        'points': lambda v: int(v or 1),
        'is_required': lambda v: 1 if v in (True, 1, '1', 'on') else 0,
        'sort_order': lambda v: int(v or 0),
    }
    for key, transform in simple.items():
        if key in data:
            fields.append(f"{key} = %s")
            vals.append(transform(data[key]))
    if 'correct_answers' in data or 'correct_answers_json' in data:
        fields.append("correct_answers_json = %s")
        vals.append(_dumps(data.get('correct_answers') or data.get('correct_answers_json') or []))
    if 'settings' in data or 'settings_json' in data:
        fields.append("settings_json = %s")
        vals.append(_dumps(data.get('settings') or data.get('settings_json') or {}))
    if not fields:
        return
    vals.append(block_id)
    cur.execute(f"UPDATE curriculum_blocks SET {', '.join(fields)} WHERE id = %s", vals)
    db.commit()

    if 'choices' in data and data['choices'] is not None:
        replace_choices(block_id, data['choices'])


def delete_block(block_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM curriculum_blocks WHERE id = %s", (block_id,))
    db.commit()


def reorder_blocks(lesson_id: int, ordered_ids: list[int]) -> None:
    db = get_db()
    cur = db.cursor()
    for i, bid in enumerate(ordered_ids):
        cur.execute(
            "UPDATE curriculum_blocks SET sort_order=%s WHERE id=%s AND lesson_id=%s",
            (i, bid, lesson_id),
        )
    db.commit()


# ── Choices ─────────────────────────────────────────────────────────────────

def list_choices(block_id: int) -> list[dict]:
    cur = _cursor()
    cur.execute(
        "SELECT * FROM curriculum_choices WHERE block_id=%s ORDER BY sort_order ASC, id ASC",
        (block_id,),
    )
    return list(cur.fetchall() or [])


def add_choice(block_id: int, label: str, is_correct: bool = False, sort_order: int = 0) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO curriculum_choices (block_id, label, is_correct, sort_order)
        VALUES (%s,%s,%s,%s)
        """,
        (block_id, (label or '').strip()[:500], 1 if is_correct else 0, int(sort_order)),
    )
    db.commit()
    return cur.lastrowid


def replace_choices(block_id: int, choices: list) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM curriculum_choices WHERE block_id=%s", (block_id,))
    for i, ch in enumerate(choices or []):
        if isinstance(ch, dict):
            label = (ch.get('label') or '').strip()
            correct = bool(ch.get('is_correct'))
        else:
            label = str(ch).strip()
            correct = False
        if not label:
            continue
        cur.execute(
            """
            INSERT INTO curriculum_choices (block_id, label, is_correct, sort_order)
            VALUES (%s,%s,%s,%s)
            """,
            (block_id, label[:500], 1 if correct else 0, i),
        )
    db.commit()


# ── Answer checking ─────────────────────────────────────────────────────────

def normalize_answer(text: str) -> str:
    t = (text or '').strip().lower()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'[^\w\s]', '', t)
    return t


def check_answer(block: dict, submitted) -> dict:
    """
    Returns {correct: bool, points_earned: int, feedback: str, correct_answers: list}
    """
    btype = block.get('block_type')
    points = int(block.get('points') or 1)
    explanation = block.get('explanation') or ''

    if btype == 'multiple_choice':
        choices = block.get('choices') or list_choices(block['id'])
        correct_ids = {int(c['id']) for c in choices if c.get('is_correct')}
        try:
            chosen = int(submitted)
        except (TypeError, ValueError):
            chosen = None
        ok = chosen in correct_ids if chosen is not None else False
        labels = [c['label'] for c in choices if c.get('is_correct')]
        return {
            'correct': ok,
            'points_earned': points if ok else 0,
            'feedback': explanation,
            'correct_answers': labels,
        }

    if btype == 'true_false':
        choices = block.get('choices') or list_choices(block['id'])
        correct = next((c for c in choices if c.get('is_correct')), None)
        if correct:
            ok = (
                str(submitted) == str(correct['id'])
                or normalize_answer(str(submitted)) == normalize_answer(correct['label'])
            )
        else:
            ok = False
        return {
            'correct': ok,
            'points_earned': points if ok else 0,
            'feedback': explanation,
            'correct_answers': [correct['label']] if correct else [],
        }

    if btype == 'fill_blank':
        accepted = block.get('correct_answers') or _loads(block.get('correct_answers_json'), [])
        if isinstance(accepted, str):
            accepted = [a.strip() for a in accepted.split('|') if a.strip()]
        # submitted may be string or list of blanks
        if isinstance(submitted, list):
            parts = [normalize_answer(x) for x in submitted]
            norms = [normalize_answer(a) for a in accepted]
            # For multi-blank: accepted list is parallel; for single accepted list is alternatives
            if len(parts) > 1 and len(norms) == len(parts):
                ok = all(p == n for p, n in zip(parts, norms))
            else:
                joined = ' '.join(parts)
                ok = joined in norms or all(p in norms for p in parts if p)
        else:
            sub = normalize_answer(str(submitted or ''))
            norms = [normalize_answer(a) for a in accepted]
            ok = sub in norms if sub else False
        return {
            'correct': ok,
            'points_earned': points if ok else 0,
            'feedback': explanation,
            'correct_answers': list(accepted),
        }

    return {'correct': True, 'points_earned': 0, 'feedback': '', 'correct_answers': []}


# ── Progress / enrollment ───────────────────────────────────────────────────

def ensure_enrollment(user_id: int, series_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT IGNORE INTO curriculum_enrollments (user_id, series_id, status)
        VALUES (%s,%s,'active')
        """,
        (user_id, series_id),
    )
    db.commit()


def record_block_answer(
    user_id: int,
    series_id: int,
    lesson_id: int,
    block_id: int,
    answer,
    result: dict,
) -> None:
    ensure_enrollment(user_id, series_id)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO curriculum_progress
            (user_id, series_id, lesson_id, block_id, status, answer_json, is_correct, score, completed_at)
        VALUES (%s,%s,%s,%s,'answered',%s,%s,%s,CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE
            answer_json=VALUES(answer_json),
            is_correct=VALUES(is_correct),
            score=VALUES(score),
            status='answered',
            completed_at=CURRENT_TIMESTAMP
        """,
        (
            user_id,
            series_id,
            lesson_id,
            block_id,
            _dumps(answer),
            1 if result.get('correct') else 0,
            int(result.get('points_earned') or 0),
        ),
    )
    db.commit()
    _refresh_enrollment_progress(user_id, series_id)


def mark_lesson_viewed(user_id: int, series_id: int, lesson_id: int) -> None:
    ensure_enrollment(user_id, series_id)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE curriculum_enrollments
        SET last_lesson_id=%s
        WHERE user_id=%s AND series_id=%s
        """,
        (lesson_id, user_id, series_id),
    )
    db.commit()
    _refresh_enrollment_progress(user_id, series_id)


def _refresh_enrollment_progress(user_id: int, series_id: int) -> None:
    cur = _cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS total FROM curriculum_blocks b
        JOIN curriculum_lessons l ON l.id = b.lesson_id
        WHERE l.series_id = %s AND l.status = 'published'
          AND b.block_type IN ('multiple_choice','true_false','fill_blank')
        """,
        (series_id,),
    )
    total = int((cur.fetchone() or {}).get('total') or 0)
    cur.execute(
        """
        SELECT COUNT(*) AS done FROM curriculum_progress
        WHERE user_id=%s AND series_id=%s AND status='answered'
        """,
        (user_id, series_id),
    )
    done = int((cur.fetchone() or {}).get('done') or 0)
    pct = round(100.0 * done / total, 2) if total else (100.0 if done else 0.0)
    # Also count lesson completion loosely: if no questions, base on last_lesson
    if total == 0:
        cur.execute(
            "SELECT COUNT(*) AS n FROM curriculum_lessons WHERE series_id=%s AND status='published'",
            (series_id,),
        )
        lessons = int((cur.fetchone() or {}).get('n') or 0)
        cur.execute(
            "SELECT last_lesson_id FROM curriculum_enrollments WHERE user_id=%s AND series_id=%s",
            (user_id, series_id),
        )
        en = cur.fetchone() or {}
        pct = 100.0 if en.get('last_lesson_id') and lessons else 0.0

    db = get_db()
    cur2 = db.cursor()
    cur2.execute(
        """
        UPDATE curriculum_enrollments
        SET progress_pct=%s,
            completed_at=IF(%s >= 100, COALESCE(completed_at, CURRENT_TIMESTAMP), NULL),
            status=IF(%s >= 100, 'completed', 'active')
        WHERE user_id=%s AND series_id=%s
        """,
        (pct, pct, pct, user_id, series_id),
    )
    db.commit()


def get_user_progress(user_id: int, series_id: int) -> dict:
    cur = _cursor()
    cur.execute(
        "SELECT * FROM curriculum_enrollments WHERE user_id=%s AND series_id=%s",
        (user_id, series_id),
    )
    enroll = cur.fetchone() or {}
    cur.execute(
        """
        SELECT block_id, is_correct, score, answer_json, status
        FROM curriculum_progress
        WHERE user_id=%s AND series_id=%s
        """,
        (user_id, series_id),
    )
    by_block = {int(r['block_id']): r for r in (cur.fetchall() or []) if r.get('block_id')}
    return {'enrollment': enroll, 'by_block': by_block}


def series_stats(series_id: int) -> dict:
    cur = _cursor()
    cur.execute(
        "SELECT COUNT(*) AS n FROM curriculum_enrollments WHERE series_id=%s",
        (series_id,),
    )
    enrolled = int((cur.fetchone() or {}).get('n') or 0)
    cur.execute(
        "SELECT COUNT(*) AS n FROM curriculum_enrollments WHERE series_id=%s AND status='completed'",
        (series_id,),
    )
    completed = int((cur.fetchone() or {}).get('n') or 0)
    cur.execute(
        "SELECT AVG(progress_pct) AS avg_pct FROM curriculum_enrollments WHERE series_id=%s",
        (series_id,),
    )
    avg_pct = float((cur.fetchone() or {}).get('avg_pct') or 0)
    return {'enrolled': enrolled, 'completed': completed, 'avg_progress': round(avg_pct, 1)}


# ── Media upload ────────────────────────────────────────────────────────────

def curriculum_upload_dir(app) -> str:
    path = os.path.join(app.config['UPLOAD_FOLDER'], 'curriculum')
    os.makedirs(path, exist_ok=True)
    return path


def save_curriculum_upload(file_storage, app, *, kind: str = 'image') -> Optional[str]:
    if not file_storage or not file_storage.filename:
        return None
    name = secure_filename(file_storage.filename)
    ext = os.path.splitext(name)[1].lower()
    allowed = IMAGE_EXTS if kind == 'image' else (IMAGE_EXTS | VIDEO_EXTS)
    if ext not in allowed:
        raise ValueError(f'Unsupported file type: {ext}')
    unique = f"{uuid.uuid4().hex[:12]}{ext}"
    dest = os.path.join(curriculum_upload_dir(app), unique)
    file_storage.save(dest)
    return unique


def youtube_embed_url(url: str) -> str:
    """Normalize YouTube/Vimeo links to embeddable URL when possible."""
    if not url:
        return ''
    url = url.strip()
    m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{6,})', url)
    if m:
        return f'https://www.youtube.com/embed/{m.group(1)}'
    m = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
    if m:
        return f'https://player.vimeo.com/video/{m.group(1)}'
    return url


def fill_blank_parts(prompt: str) -> list:
    """
    Split a fill-in-the-blank prompt on ___ or {{blank}} markers.
    Returns alternating text/blank segments: [{type:text|blank, value}]
    """
    if not prompt:
        return [{'type': 'text', 'value': ''}]
    parts = re.split(r'(\{\{blank\}\}|_{3,})', prompt)
    out = []
    for p in parts:
        if not p:
            continue
        if re.fullmatch(r'\{\{blank\}\}|_{3,}', p):
            out.append({'type': 'blank', 'value': ''})
        else:
            out.append({'type': 'text', 'value': p})
    if not any(x['type'] == 'blank' for x in out):
        # No markers — single blank after the prompt
        out.append({'type': 'blank', 'value': ''})
    return out
