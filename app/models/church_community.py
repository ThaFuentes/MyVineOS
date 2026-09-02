# Church page + member space helpers. Strip always uses the PAGE OWNER's campus.

from __future__ import annotations

from typing import Any, Optional

import pymysql
from flask import g, has_request_context, session

from app.models.db import get_db


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def church_name() -> str:
    if has_request_context():
        settings = getattr(g, 'settings', None) or {}
        name = (settings.get('church_name') or '').strip()
        if name:
            return name
    try:
        cur = _cur()
        cur.execute("SELECT church_name FROM settings WHERE id = 1")
        row = cur.fetchone() or {}
        return (row.get('church_name') or '').strip() or 'Church'
    except Exception:
        return 'Church'


def single_church_install() -> bool:
    """Self-host is one church. Branch pages only exist when multi-campus is on with 2+ campuses."""
    if has_request_context() and hasattr(g, '_single_church_install'):
        return bool(g._single_church_install)
    result = True
    try:
        from app.models import campuses as campus_model
        if campus_model.multi_campus_enabled():
            result = len(campus_model.list_campuses(active_only=True) or []) <= 1
    except Exception:
        result = True
    if has_request_context():
        g._single_church_install = result
    return result


def canonical_page_id(campus_id: int | None = None) -> int:
    if single_church_install():
        return 0
    return int(campus_id or 0)


def church_home_href(campus_id: int | None = None) -> str:
    from flask import url_for
    if not has_request_context():
        return '/church/'
    if single_church_install() or not campus_id:
        return url_for('church.church_home')
    return url_for('church.church_home', campus_id=int(campus_id))


def resolve_campus(campus_id: int | None = None, user_id: int | None = None) -> Optional[dict]:
    """Campus for a church page or for a person. None = single-church / primary."""
    from app.models import campuses as campus_model

    if campus_id:
        campus = campus_model.get_campus(int(campus_id))
        if campus and campus.get('is_active'):
            return campus
    if user_id:
        home_id = campus_model.user_home_campus_id(int(user_id))
        if home_id:
            campus = campus_model.get_campus(home_id)
            if campus:
                return campus
    if campus_model.multi_campus_enabled():
        return campus_model.get_primary_campus()
    campuses = campus_model.list_campuses(active_only=True)
    if len(campuses) == 1:
        return campuses[0]
    return campus_model.get_primary_campus() or (campuses[0] if campuses else None)


def get_church_page(campus_id: int = 0) -> dict:
    cur = _cur()
    try:
        cur.execute("SELECT * FROM church_pages WHERE campus_id = %s", (int(campus_id or 0),))
        return cur.fetchone() or {}
    except Exception:
        return {}


def get_canonical_church_page(campus_id: int | None = 0) -> dict:
    """One church page for this install (campus_id=0) unless real multi-campus branches exist."""
    cid = canonical_page_id(campus_id)
    page = dict(get_church_page(cid) or {})
    if cid != 0:
        return page
    missing = not page.get('hero_path') or not page.get('portrait_path') or not page.get('about')
    if not missing:
        return page
    try:
        cur = _cur()
        cur.execute("SELECT * FROM church_pages WHERE campus_id <> 0")
        for row in cur.fetchall() or []:
            for key in (
                'hero_path', 'portrait_path', 'about', 'verse',
                'accent_color', 'bg_color', 'text_color', 'banner_x', 'banner_y',
            ):
                if not page.get(key) and row.get(key):
                    page[key] = row.get(key)
    except Exception:
        pass
    return page


def save_church_page(campus_id: int, about: str, verse: str, user_id: int | None, colors: dict | None = None) -> None:
    db = get_db()
    cur = db.cursor()
    colors = colors or {}
    cur.execute(
        """
        INSERT INTO church_pages (campus_id, about, verse, updated_by, accent_color, bg_color, text_color)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            about = VALUES(about),
            verse = VALUES(verse),
            updated_by = VALUES(updated_by),
            accent_color = VALUES(accent_color),
            bg_color = VALUES(bg_color),
            text_color = VALUES(text_color)
        """,
        (
            int(campus_id or 0),
            about or None,
            (verse or '')[:255] or None,
            user_id,
            colors.get('accent_color'),
            colors.get('bg_color'),
            colors.get('text_color'),
        ),
    )
    db.commit()


def get_member_space(user_id: int) -> Optional[dict]:
    cur = _cur()
    try:
        cur.execute("SELECT * FROM member_spaces WHERE user_id = %s", (int(user_id),))
        return cur.fetchone()
    except Exception:
        return None


def create_member_space(user_id: int, about: str = '', favorite_verse: str = '') -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO member_spaces (user_id, about, favorite_verse)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            about = COALESCE(VALUES(about), about),
            favorite_verse = COALESCE(VALUES(favorite_verse), favorite_verse)
        """,
        (int(user_id), about or None, (favorite_verse or '')[:255] or None),
    )
    db.commit()


def update_member_space(user_id: int, data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    args_full = (
        data.get('about') or None,
        (data.get('favorite_verse') or '')[:255] or None,
        1 if data.get('show_to_visitors') else 0,
        1 if data.get('show_training') else 0,
        1 if data.get('allow_messages') else 0,
        1 if data.get('show_stats') else 0,
        1 if data.get('allow_guest_comments') else 0,
        data.get('accent_color') or None,
        data.get('bg_color') or None,
        data.get('text_color') or None,
        (data.get('hometown') or '')[:160] or None,
        (data.get('occupation') or '')[:160] or None,
        (data.get('interests') or '')[:500] or None,
        data.get('banner_pos') if data.get('banner_pos') in ('top', 'center', 'bottom') else None,
        1 if data.get('show_replies') else 0,
        0 if data.get('show_church_feed') in (0, False, '0') else 1,
        0 if data.get('show_follows') in (0, False, '0') else 1,
        0 if data.get('show_in_directory') in (0, False, '0') else 1,
        1 if data.get('page_private') else 0,
        int(user_id),
    )
    try:
        cur.execute(
            """
            UPDATE member_spaces
            SET about = %s,
                favorite_verse = %s,
                show_to_visitors = %s,
                show_training = %s,
                allow_messages = %s,
                show_stats = %s,
                allow_guest_comments = %s,
                accent_color = %s,
                bg_color = %s,
                text_color = %s,
                hometown = %s,
                occupation = %s,
                interests = %s,
                banner_pos = %s,
                show_replies = %s,
                show_church_feed = %s,
                show_follows = %s,
                show_in_directory = %s,
                page_private = %s
            WHERE user_id = %s
            """,
            args_full,
        )
        db.commit()
        return
    except Exception:
        db.rollback()
        cur.execute(
            """
            UPDATE member_spaces
            SET about = %s, favorite_verse = %s, show_to_visitors = %s, show_training = %s,
                allow_messages = %s, show_stats = %s, allow_guest_comments = %s,
                accent_color = %s, bg_color = %s, text_color = %s, hometown = %s,
                occupation = %s, interests = %s, banner_pos = %s, show_replies = %s,
                show_church_feed = %s, show_in_directory = %s, page_private = %s
            WHERE user_id = %s
            """,
            (
                data.get('about') or None,
                (data.get('favorite_verse') or '')[:255] or None,
                1 if data.get('show_to_visitors') else 0,
                1 if data.get('show_training') else 0,
                1 if data.get('allow_messages') else 0,
                1 if data.get('show_stats') else 0,
                1 if data.get('allow_guest_comments') else 0,
                data.get('accent_color') or None,
                data.get('bg_color') or None,
                data.get('text_color') or None,
                (data.get('hometown') or '')[:160] or None,
                (data.get('occupation') or '')[:160] or None,
                (data.get('interests') or '')[:500] or None,
                data.get('banner_pos') if data.get('banner_pos') in ('top', 'center', 'bottom') else None,
                1 if data.get('show_replies') else 0,
                0 if data.get('show_church_feed') in (0, False, '0') else 1,
                0 if data.get('show_in_directory') in (0, False, '0') else 1,
                1 if data.get('page_private') else 0,
                int(user_id),
            ),
        )
        db.commit()


def get_user_public(user_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT id, username, first_name, last_name, primary_campus_id,
               birthday, show_birthday, phone, address
        FROM users WHERE id = %s
        """,
        (int(user_id),),
    )
    return cur.fetchone()


def get_user_by_username(username: str) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT id, username, first_name, last_name, primary_campus_id, role,
               birthday, show_birthday, phone, address
        FROM users WHERE username = %s
        """,
        (username,),
    )
    return cur.fetchone()


def scheduler_upcoming() -> dict:
    """Exact next service the Pastoral Command Center uses (templates + that week's override)."""
    try:
        from app.models.pastoral.service_plans import get_upcoming_service
        return get_upcoming_service() or {}
    except Exception as exc:
        print(f'scheduler_upcoming: {exc}')
        return {}


def _fmt_clock(value) -> str:
    if value is None or value == '':
        return ''
    if hasattr(value, 'strftime') and not isinstance(value, str):
        try:
            return value.strftime('%-I:%M %p')
        except Exception:
            return value.strftime('%I:%M %p').lstrip('0')
    raw = str(value).strip()
    for fmt in ('%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M%p'):
        try:
            from datetime import datetime as dt
            return dt.strptime(raw[:8] if fmt == '%H:%M:%S' else raw, fmt).strftime('%-I:%M %p')
        except Exception:
            continue
    return raw


def publish_service_plan_update(user_id: int | None) -> None:
    """Put the current next-service plan on the official church wall (public)."""
    if not user_id:
        return
    plan = scheduler_upcoming()
    if not plan or not (plan.get('title') or plan.get('service_date') or plan.get('filled_roles')):
        return
    from datetime import datetime as dt
    from flask import url_for

    sd = plan.get('service_date')
    if hasattr(sd, 'strftime'):
        date_label = sd.strftime('%A, %B %d, %Y')
    else:
        raw = str(sd or plan.get('date_str') or '')[:10]
        try:
            date_label = dt.strptime(raw, '%Y-%m-%d').strftime('%A, %B %d, %Y')
        except Exception:
            date_label = raw
    title = (plan.get('title') or 'Upcoming service').strip()[:255]
    lines = [date_label] if date_label else []
    bits = []
    start = _fmt_clock(plan.get('start_time'))
    worship = _fmt_clock(plan.get('worship_start_time'))
    if start:
        bits.append(f'Service {start}')
    if worship:
        bits.append(f'Worship {worship}')
    if bits:
        lines.append(' · '.join(bits))
    for role in plan.get('filled_roles') or []:
        role_name = (role.get('role_name') or '').strip()
        name = (role.get('name') or '').strip()
        if role_name and name:
            lines.append(f'{role_name}: {name}')
    href = '/church/'
    try:
        href = url_for('church.church_home')
    except Exception:
        pass
    publish_church_notice(user_id, title, '\n'.join(lines), href=href)


def publish_church_notice(user_id: int | None, title: str, body: str, href: str = '', campus_id: int = 0) -> None:
    """Official church/branch wall item. Worship/pastor saves use this without page-edit rights."""
    if not user_id:
        return
    from app.models import social as social_model

    title = (title or 'Church update').strip()[:255]
    body = (body or '').strip()[:8000]
    href = href or '/church/'
    voice = 'campus' if int(campus_id or 0) else 'church'
    db = get_db()
    cur = db.cursor()
    post_id = None
    try:
        cur.execute(
            """
            SELECT p.id FROM community_posts p
            INNER JOIN content_posting cp
              ON cp.content_id = p.id AND cp.content_type = p.kind AND cp.posted_as = %s
            WHERE p.kind='post' AND p.title=%s
              AND p.created_at >= (NOW() - INTERVAL 3 DAY)
              AND (cp.campus_id = %s OR %s = 0)
            ORDER BY p.id DESC LIMIT 1
            """,
            (voice, title, int(campus_id or 0), int(campus_id or 0)),
        )
        row = cur.fetchone()
        if row:
            post_id = int(row[0] if not isinstance(row, dict) else row['id'])
            cur.execute(
                "UPDATE community_posts SET body=%s, url=%s, visibility='public', created_at=NOW(), user_id=%s WHERE id=%s",
                (body, href, int(user_id), post_id),
            )
            db.commit()
    except Exception as exc:
        print(f'publish_church_notice lookup: {exc}')
        post_id = None
    if not post_id:
        post_id = social_model.create_post(int(user_id), 'post', title, body, href, 'public')
        if post_id:
            record_posting('post', post_id, voice, int(campus_id or 0), int(user_id))


def publish_worship_update(user_id: int | None, setlist: dict | None = None, template: dict | None = None) -> None:
    """Worship team schedule → church page wall, no page-editor required."""
    row = setlist or template or {}
    if not row:
        return
    from flask import url_for

    raw_title = (row.get('title') or 'Worship team').strip() or 'Worship team'
    title = raw_title if raw_title.lower().startswith('worship') else f'Worship · {raw_title}'
    title = title[:255]
    sd = row.get('service_date')
    date_label = ''
    if hasattr(sd, 'strftime'):
        date_label = sd.strftime('%A, %B %d, %Y')
    elif sd:
        date_label = str(sd)[:10]
    weekday = (row.get('weekday_name') or '').strip()
    if weekday and not date_label:
        date_label = f'Every {weekday}'
    lines = [p for p in (date_label,) if p]
    bits = []
    service = _fmt_clock(row.get('service_time') or row.get('start_time'))
    rehearsal = _fmt_clock(row.get('rehearsal_time'))
    if service:
        bits.append(f'Service {service}')
    if rehearsal:
        bits.append(f'Rehearsal {rehearsal}')
    if bits:
        lines.append(' · '.join(bits))
    for assignment in row.get('assignments') or []:
        role_name = (assignment.get('role_name') or '').strip()
        name = (
            (assignment.get('user_full_name') or '').strip()
            or (assignment.get('guest_name') or '').strip()
            or (assignment.get('name') or '').strip()
        )
        if role_name and name:
            lines.append(f'{role_name}: {name}')
    href = '/church/'
    try:
        href = url_for('church.church_home')
    except Exception:
        pass
    publish_church_notice(user_id, title, '\n'.join(lines), href=href)


def empty_gathering() -> dict:
    return {
        'title': '',
        'speaker': '',
        'speaker_id': None,
        'speaker_username': '',
        'speaker_page_url': '',
        'start_time': '',
        'date_label': '',
        'date_str': '',
        'is_override': False,
        'branch_name': '',
    }


def _speaker_username(svc: dict) -> str:
    uname = (svc.get('preacher_username') or '').strip()
    uid = svc.get('preacher_id')
    if uname or not uid:
        return uname
    try:
        user = get_user_public(int(uid))
    except Exception:
        user = None
    return ((user or {}).get('username') or '').strip()


def gathering_from_service(svc: dict, campus: dict | None = None) -> dict:
    branch = ''
    if campus and not single_church_install():
        branch = (campus.get('short_name') or campus.get('name') or '').strip()
    uname = _speaker_username(svc)
    speaker = (svc.get('preacher') or '').strip()
    if not speaker and campus:
        speaker = (campus.get('pastor_name') or '').strip()
    return {
        'title': svc.get('title') or 'Service',
        'speaker': speaker,
        'speaker_id': int(svc['preacher_id']) if svc.get('preacher_id') else None,
        'speaker_username': uname,
        'speaker_page_url': f'/church/u/{uname}' if uname else '',
        'start_time': svc.get('start_time') or svc.get('worship_start_time') or '',
        'date_label': svc.get('date_label') or '',
        'date_str': svc.get('date_str') or '',
        'is_override': bool(svc.get('is_override')),
        'branch_name': branch,
    }


def upcoming_gatherings(campus: dict | None = None, limit: int = 2) -> list[dict]:
    """Next services from pastoral scheduling (weekday template + dated weekly overrides)."""
    try:
        from app.models.pastoral.service_plans import get_upcoming_services_display
        services = get_upcoming_services_display(limit=max(int(limit), 1), days_ahead=90) or []
    except Exception as exc:
        print(f'upcoming_gatherings: {exc}')
        services = []
    out = [gathering_from_service(svc, campus) for svc in services]
    if out:
        return out
    empty = empty_gathering()
    if campus and campus.get('pastor_name') and not single_church_install():
        empty['speaker'] = campus.get('pastor_name')
        empty['branch_name'] = (campus.get('short_name') or campus.get('name') or '').strip()
    elif not out:
        settings = getattr(g, 'settings', None) or {} if has_request_context() else {}
        empty['speaker'] = (settings.get('pastor') or '').strip()
    return [empty] if empty.get('speaker') else []


def next_gathering_for_campus(campus: dict | None) -> dict:
    """
    Next service: who's speaking + start time.
    Reads the pastoral scheduler (recurring template, then that week's dated override).
    """
    rows = upcoming_gatherings(campus, limit=1)
    return rows[0] if rows else empty_gathering()


def church_context_for_user(user_id: int | None) -> dict:
    """Strip data for a member page — always this church (and the owner's campus only if multi-campus)."""
    one = single_church_install()
    campus = None if one else (resolve_campus(user_id=user_id) if user_id else None)
    gatherings = upcoming_gatherings(campus, limit=2)
    gathering = gatherings[0] if gatherings else empty_gathering()
    upcoming = gatherings[1] if len(gatherings) > 1 else None
    upcoming_service = scheduler_upcoming()
    if not gathering.get('speaker'):
        for role in upcoming_service.get('filled_roles') or []:
            if (role.get('role_name') or '').lower().strip() in (
                'preacher', 'pastor', 'speaker', 'guest speaker', 'guest preacher',
            ):
                gathering['speaker'] = (role.get('name') or '').strip()
                break
    page = get_canonical_church_page(campus.get('id') if campus else 0)
    banner_url = ''
    pic_url = ''
    try:
        from app.models import social as social_model
        pic_url = social_model.identity_url((page or {}).get('portrait_path'))
        banner_url = social_model.identity_url((page or {}).get('hero_path'))
    except Exception:
        pic_url = ''
        banner_url = ''
    speaking = []
    if user_id:
        for row in gatherings:
            if row.get('speaker_id') and int(row['speaker_id']) == int(user_id):
                speaking.append(row)
    campus_id = 0 if one else int((campus or {}).get('id') or 0)
    loc = profile_contact(campus)
    return {
        'church_name': church_name(),
        'branch_name': '' if one else (gathering.get('branch_name') or (campus.get('name') if campus else '') or ''),
        'campus_id': campus_id,
        'campus_code': '' if one else ((campus.get('code') if campus else '') or ''),
        'page_url': church_home_href(campus_id),
        'pic_url': pic_url,
        'banner_url': banner_url,
        'speaker': gathering.get('speaker') or '',
        'speaker_id': gathering.get('speaker_id'),
        'speaker_page_url': gathering.get('speaker_page_url') or '',
        'start_time': gathering.get('start_time') or '',
        'date_label': gathering.get('date_label') or '',
        'title': gathering.get('title') or '',
        'is_override': bool(gathering.get('is_override')),
        'upcoming': upcoming,
        'speaking': speaking,
        'gathering': gathering,
        'upcoming_service': upcoming_service,
        'filled_roles': upcoming_service.get('filled_roles') or [],
        'address': loc.get('address') or '',
        'city': loc.get('city') or '',
        'state': loc.get('state') or '',
        'phone': loc.get('phone') or '',
    }


# Official church-ish types when a row has no explicit posting voice yet.
CHURCH_VOICE_TYPES = ('announcement', 'event', 'sermon')


def _session_role() -> str:
    if has_request_context():
        return (session.get('user_role') or '').strip()
    return ''


def _session_uid() -> int | None:
    if has_request_context() and session.get('user_id'):
        try:
            return int(session.get('user_id'))
        except (TypeError, ValueError):
            return None
    return None


def _page_grant(campus_id: int | None, user_id: int | None) -> str:
    """editor_role on church_page_editors, or ''."""
    if not user_id:
        return ''
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT editor_role FROM church_page_editors
            WHERE user_id = %s AND campus_id = %s
            LIMIT 1
            """,
            (int(user_id), int(campus_id or 0)),
        )
        row = cur.fetchone() or {}
        return (row.get('editor_role') or '').strip().lower()
    except Exception:
        return ''


def can_edit_church_page(campus_id: int | None = 0) -> bool:
    """Look, about, photos. Owner / Admin, or assigned editor/admin — not poster."""
    if not has_request_context():
        return False
    if _session_role() in ('Owner', 'Admin'):
        return True
    return _page_grant(campus_id, _session_uid()) in ('editor', 'admin')


def _ministry_posts_to_main_church(user_id: int | None) -> bool:
    """Worship managers and pastoral staff feed the main church wall by doing their job."""
    if not user_id:
        return False
    try:
        from app.models.worship.shared import can_manage_worship
        if can_manage_worship(int(user_id)):
            return True
    except Exception:
        pass
    try:
        from app.models.pastoral.shared import is_in_pastoral_group
        if is_in_pastoral_group(int(user_id)):
            return True
    except Exception:
        pass
    return False


def can_post_church_updates(campus_id: int | None = 0) -> bool:
    """Official updates on a church/branch wall — not the same as changing the look.

    Look editors can always post. Poster is a grant for people who should write
    as the church without touching banner/about. Worship managers and pastoral
    staff do not need a grant: their schedules still publish on the main church
    page (campus 0), and they may compose as the church there.
    """
    if can_edit_church_page(campus_id):
        return True
    uid = _session_uid()
    if not uid:
        return False
    if _page_grant(campus_id, uid) == 'poster':
        return True
    if int(campus_id or 0) == 0 and _ministry_posts_to_main_church(uid):
        return True
    return False


def list_automatic_church_posters() -> list[dict]:
    """People whose ministry tools already land on the main church wall."""
    seen: set[int] = set()
    out: list[dict] = []

    def _add(row: dict, why: str) -> None:
        try:
            uid = int(row.get('id') or row.get('user_id') or 0)
        except (TypeError, ValueError):
            return
        if not uid or uid in seen:
            return
        role = (row.get('role') or row.get('site_role') or '').strip()
        if role in ('Owner', 'Admin'):
            return
        seen.add(uid)
        name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
        out.append({
            'user_id': uid,
            'username': row.get('username') or '',
            'display_name': name or row.get('username') or 'Member',
            'why': why,
        })

    try:
        from app.models.worship.shared import get_worship_leaders
        for row in get_worship_leaders() or []:
            if (row.get('role_in_group') or '') == 'leader':
                _add(row, 'Worship team leader — setlists and weekly templates show here even if they are not page editors')
    except Exception:
        pass
    try:
        from app.models.pastoral.shared import get_pastoral_team_members
        for row in get_pastoral_team_members() or []:
            _add(row, 'Pastoral staff — service-plan saves show here even if they are not page editors')
    except Exception:
        pass
    return out


def can_assign_page_editors(campus_id: int | None = 0) -> bool:
    if _session_role() in ('Owner', 'Admin'):
        return True
    uid = _session_uid()
    if not uid:
        return False
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT editor_role FROM church_page_editors
            WHERE user_id = %s AND campus_id = %s AND editor_role = 'admin'
            LIMIT 1
            """,
            (uid, int(campus_id or 0)),
        )
        return bool(cur.fetchone())
    except Exception:
        return False


def list_page_editors(campus_id: int | None = 0) -> list[dict]:
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT e.user_id, e.editor_role, e.campus_id,
                   u.username, u.first_name, u.last_name, u.role
            FROM church_page_editors e
            JOIN users u ON u.id = e.user_id
            WHERE e.campus_id = %s
            ORDER BY FIELD(e.editor_role, 'admin', 'editor', 'poster'), u.first_name, u.last_name
            """,
            (int(campus_id or 0),),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        rows = []
    out = []
    for row in rows:
        name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
        out.append({
            **row,
            'display_name': name or row.get('username'),
        })
    return out


def add_page_editor(campus_id: int, user_id: int, editor_role: str, added_by: int | None) -> tuple[bool, str]:
    role = (editor_role or 'editor').strip().lower()
    if role not in ('admin', 'editor', 'poster'):
        role = 'editor'
    try:
        cur = _cur()
        cur.execute("SELECT id, role, username FROM users WHERE id = %s", (int(user_id),))
        user = cur.fetchone()
        if not user:
            return False, 'No member with that name.'
        if user.get('role') == 'Owner':
            return False, 'The Owner already can edit every church page.'
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO church_page_editors (campus_id, user_id, editor_role, added_by)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE editor_role = VALUES(editor_role)
            """,
            (int(campus_id or 0), int(user_id), role, added_by),
        )
        db.commit()
        labels = {
            'poster': 'Poster — they can add to this wall, not change the look',
            'editor': 'Editor — look and posts',
            'admin': 'Page admin — look, posts, and who is on this list',
        }
        return True, f"Added {(user.get('username') or 'member')} as {labels.get(role, role)}."
    except Exception:
        return False, 'Could not add that person.'


def remove_page_editor(campus_id: int, user_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM church_page_editors WHERE campus_id = %s AND user_id = %s",
        (int(campus_id or 0), int(user_id)),
    )
    db.commit()


def record_posting(content_type: str, content_id: int | None, posted_as: str,
                   campus_id: int = 0, user_id: int | None = None) -> None:
    if not content_id:
        return
    posted_as = posted_as if posted_as in ('member', 'church', 'campus') else 'member'
    campus_id = int(campus_id or 0)
    if posted_as == 'church':
        campus_id = 0
    if posted_as == 'campus' and not campus_id:
        posted_as = 'church'
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO content_posting (content_type, content_id, posted_as, campus_id, user_id)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                posted_as = VALUES(posted_as),
                campus_id = VALUES(campus_id),
                user_id = VALUES(user_id)
            """,
            ((content_type or '').strip(), int(content_id), posted_as, campus_id, user_id),
        )
        db.commit()
    except Exception as exc:
        print(f"record_posting: {exc}")


def get_postings(pairs: list[tuple[str, int]]) -> dict:
    clean = []
    for kind, oid in pairs or []:
        try:
            if kind and oid:
                clean.append((str(kind), int(oid)))
        except (TypeError, ValueError):
            continue
    if not clean:
        return {}
    try:
        cur = _cur()
        placeholders = ','.join(['(%s,%s)'] * len(clean))
        args: list = []
        for kind, oid in clean:
            args.extend([kind, oid])
        cur.execute(
            f"SELECT content_type, content_id, posted_as, campus_id, user_id "
            f"FROM content_posting WHERE (content_type, content_id) IN ({placeholders})",
            args,
        )
        out = {}
        for row in cur.fetchall() or []:
            out[(row['content_type'], int(row['content_id']))] = row
        return out
    except Exception:
        return {}


def infer_posting(kind: str, item_id: int | None, mapped: dict | None = None) -> dict:
    if mapped:
        return {
            'posted_as': mapped.get('posted_as') or 'member',
            'campus_id': int(mapped.get('campus_id') or 0),
        }
    if (kind or '') in CHURCH_VOICE_TYPES and item_id:
        return {'posted_as': 'church', 'campus_id': 0}
    return {'posted_as': 'member', 'campus_id': 0}


def posting_label(meta: dict, campus: dict | None = None) -> str:
    voice = (meta or {}).get('posted_as') or 'member'
    if voice == 'church':
        return church_name()
    if voice == 'campus':
        if campus:
            return (campus.get('short_name') or campus.get('name') or 'Branch').strip()
        return 'Branch'
    return ''


def compose_voices() -> list[dict]:
    voices = [{'key': 'member', 'label': 'You', 'hint': 'Goes on your personal page'}]
    if can_post_church_updates(0):
        voices.append({
            'key': 'church',
            'label': church_name(),
            'hint': 'Official church page — not your personal wall',
        })
    try:
        from app.models import campuses as campus_model
        if campus_model.multi_campus_enabled() and not single_church_install():
            for row in campus_model.list_campuses(active_only=True):
                cid = int(row.get('id') or 0)
                if not cid or not can_post_church_updates(cid):
                    continue
                label = (row.get('short_name') or row.get('name') or f'Branch {cid}').strip()
                voices.append({
                    'key': f'campus:{cid}',
                    'label': label,
                    'hint': 'This branch page only',
                })
    except Exception:
        pass
    return voices


def default_compose_voice() -> str:
    if has_request_context():
        saved = (session.get('compose_voice') or '').strip()
        path = (request_path() or '').rstrip('/') or '/'
        if path.startswith('/church/u/'):
            return 'member'
        if path.startswith('/church/c/'):
            try:
                cid = int(path.split('/church/c/', 1)[1].split('/', 1)[0])
            except (TypeError, ValueError):
                cid = 0
            if cid and can_post_church_updates(cid):
                return f'campus:{cid}'
        if path in ('', '/', '/church') or path.startswith('/church'):
            if can_post_church_updates(0):
                return 'church'
        allowed = {v['key'] for v in compose_voices()}
        if saved in allowed:
            return saved
    return 'member'


def request_path() -> str:
    if not has_request_context():
        return ''
    from flask import request
    return request.path or ''


def resolve_compose_voice(raw: str | None) -> dict:
    allowed = {v['key']: v for v in compose_voices()}
    key = (raw or '').strip() or default_compose_voice()
    if key not in allowed:
        key = 'member'
    if key == 'church':
        return {'key': 'church', 'posted_as': 'church', 'campus_id': 0, 'label': allowed[key]['label']}
    if key.startswith('campus:'):
        try:
            cid = int(key.split(':', 1)[1])
        except (TypeError, ValueError):
            cid = 0
        if cid and key in allowed:
            return {'key': key, 'posted_as': 'campus', 'campus_id': cid, 'label': allowed[key]['label']}
    return {'key': 'member', 'posted_as': 'member', 'campus_id': 0, 'label': 'You'}


def landing_for_voice(voice: dict, nxt: str) -> str:
    """Stay on the matching page. If they posted as the other identity, send them there."""
    from flask import url_for
    path = (nxt or '').split('?', 1)[0]
    posted_as = (voice or {}).get('posted_as') or 'member'
    on_member = '/church/u/' in path
    on_church = (
        path.rstrip('/') in ('', '/church')
        or path == '/'
        or path.startswith('/church/c/')
        or path.rstrip('/') == '/church'
    )
    if posted_as == 'member' and on_church:
        username = session.get('username') if has_request_context() else ''
        if username:
            return url_for('church.member_page', username=username)
        return nxt
    if posted_as == 'church' and on_member:
        return url_for('church.church_home')
    if posted_as == 'campus' and on_member:
        cid = int((voice or {}).get('campus_id') or 0)
        if cid:
            return url_for('church.church_home', campus_id=cid)
        return url_for('church.church_home')
    return nxt or path or '/'


def attach_feed_rank(items: list[dict], viewer_id: int | None = None) -> list[dict]:
    """Follows first, then the viewer's branch, then the rest of the church."""
    if not items:
        return items
    from app.models import social as social_model

    follows = set(social_model.following_ids(viewer_id)) if viewer_id else set()
    home = 0
    branched = (not single_church_install())
    if viewer_id and branched:
        try:
            from app.models import campuses as campus_model
            home = int(campus_model.user_home_campus_id(int(viewer_id)) or 0)
        except Exception:
            home = 0
    pairs = [(item.get('type'), item.get('id')) for item in items]
    mapped = get_postings(pairs)
    for item in items:
        kind = item.get('type')
        oid = item.get('id')
        meta = infer_posting(kind, oid, mapped.get((kind, int(oid))) if oid else None)
        if not item.get('posted_as'):
            item['posted_as'] = meta.get('posted_as')
        campus_id = int(item.get('campus_id') or item.get('primary_campus_id') or meta.get('campus_id') or 0)
        item['campus_id'] = campus_id
        author_id = int(item.get('author_id') or item.get('user_id') or 0)
        item['author_id'] = author_id
        from_follow = bool(author_id and author_id in follows)
        item['from_follow'] = from_follow
        if from_follow:
            item['feed_rank'] = 0
            item['group'] = 'People you follow'
        elif home and campus_id == home:
            item['feed_rank'] = 1
            item['group'] = 'Your branch'
        else:
            item['feed_rank'] = 2
            item['group'] = 'Church family' if viewer_id else item.get('group') or 'Church family'

    def _key(item):
        dt = item.get('sort_dt')
        ts = 0.0
        if dt is not None and hasattr(dt, 'timestamp'):
            try:
                ts = float(dt.timestamp())
            except Exception:
                ts = 0.0
        return (int(item.get('feed_rank') or 2), -ts)

    if viewer_id:
        items.sort(key=_key)
    return items


def item_visible_to(item: dict, viewer_id: int | None, owner_id: int | None = None, surface: str = 'wall') -> bool:
    """public = guests; private = signed-in; personal = owner on their own wall only."""
    vis = (item.get('visibility') or 'public').strip()
    author = item.get('author_id') or item.get('user_id') or owner_id
    try:
        author_i = int(author) if author else 0
    except (TypeError, ValueError):
        author_i = 0
    is_owner = bool(viewer_id and author_i and int(viewer_id) == author_i)
    if vis == 'personal':
        return is_owner and surface == 'wall'
    if vis == 'public':
        return True
    if vis in ('private', 'followers'):
        return bool(viewer_id)
    return False


def visible_items(
    items: list[dict],
    viewer_id: int | None,
    owner_id: int | None = None,
    surface: str = 'wall',
    query: str = '',
) -> list[dict]:
    out = []
    needle = (query or '').strip().lower()
    for item in items or []:
        if not item_visible_to(item, viewer_id, owner_id=owner_id, surface=surface):
            continue
        if needle:
            blob = ' '.join(
                str(item.get(k) or '')
                for k in ('title', 'body', 'author', 'creator_name', 'type_label', 'type')
            ).lower()
            if needle not in blob:
                continue
        out.append(item)
    return out


TYPE_LABELS = {
    'event': 'Event',
    'prayer': 'Prayer',
    'sermon': 'Sermon',
    'announcement': 'Update',
    'dream': 'Dream',
    'prophecy': 'Prophecy',
    'comment': 'Comment',
    'post': 'Post',
    'blog': 'Blog',
    'book': 'Book',
    'badge': 'Study',
    'quote': 'Quote',
    'verse': 'Verse',
    'image': 'Photo',
}


def main_campus() -> Optional[dict]:
    from app.models import campuses as campus_model
    return campus_model.get_primary_campus()


def branch_directory(exclude_id: int | None = None) -> list[dict]:
    from app.models import campuses as campus_model

    if single_church_install() or not campus_model.multi_campus_enabled():
        return []
    rows = campus_model.list_campuses(active_only=True)
    cards = []
    for row in rows:
        cid = int(row.get('id') or 0)
        if exclude_id and cid == int(exclude_id):
            continue
        gathering = next_gathering_for_campus(row)
        cards.append({
            **row,
            'gathering': gathering,
            'page_url': f'/church/c/{cid}',
        })
    return cards if len(rows) > 1 else []


def profile_contact(campus: Optional[dict] = None) -> dict:
    settings = {}
    if has_request_context():
        settings = getattr(g, 'settings', None) or {}
    campus = campus or {}
    address = (campus.get('address') or settings.get('address') or '').strip()
    city = (campus.get('city') or settings.get('city') or '').strip()
    state = (campus.get('state') or settings.get('state') or '').strip()
    parts = [address]
    if city and city.lower() not in address.lower():
        parts.append(city)
    if state and state.lower() not in address.lower():
        parts.append(state)
    line = ', '.join(p for p in parts if p)
    return {
        'pastor': (campus.get('pastor_name') or settings.get('pastor') or '').strip(),
        'address': address,
        'phone': (campus.get('phone') or settings.get('phone_number') or '').strip(),
        'email': (campus.get('email') or settings.get('email') or settings.get('church_email') or '').strip(),
        'city': city,
        'state': state,
        'line': line,
    }


def church_wall(include_members: bool = False, limit: int = 24, campus_id: int = 0) -> list[dict]:
    """Official church / branch wall only — not personal member posts."""
    try:
        from app.routes.public.public_dashboard.queries import get_public_dashboard_feed
        from app.routes.public.public_dashboard.utils import censor_public_content
        from app.utils.helpers import censor_text as _censor
        from app.utils.appearance import safe_url_for
        from app.utils.time_utils import format_church

        feed = get_public_dashboard_feed(limit=max(limit * 3, 40), include_members=include_members) or []
        feed = censor_public_content(feed)
        detail = {
            'event': ('public.public_events.public_event_detail', 'event_id'),
            'sermon': ('public.public_sermons.public_sermon_detail', 'sermon_id'),
            'announcement': ('public.public_announcements.public_announcement_detail', 'ann_id'),
            'dream': ('public.public_dreams.public_dream_detail', 'dream_id'),
            'prophecy': ('public.public_prophecies.public_prophecy_detail', 'prophecy_id'),
            'prayer': ('public.public_prayers.public_prayer_detail', 'prayer_id'),
        }
        pairs = [(item.get('type'), item.get('id')) for item in feed]
        mapped = get_postings(pairs)
        wall_campus = int(campus_id or 0)
        campus_row = None
        if wall_campus:
            try:
                from app.models import campuses as campus_model
                campus_row = campus_model.get_campus(wall_campus)
            except Exception:
                campus_row = None
        official = church_name() if wall_campus == 0 else (
            (campus_row.get('short_name') or campus_row.get('name') or 'Branch') if campus_row else 'Branch'
        )
        out = []
        for item in feed:
            kind = item.get('type')
            oid = item.get('id')
            meta = infer_posting(kind, oid, mapped.get((kind, int(oid))) if oid else None)
            if wall_campus == 0:
                if meta.get('posted_as') != 'church':
                    continue
            else:
                if meta.get('posted_as') != 'campus' or int(meta.get('campus_id') or 0) != wall_campus:
                    continue
            item['title'] = _censor(item.get('title') or item.get('event_name') or '')
            body = item.get('body') or item.get('description') or item.get('content') or ''
            item['body'] = _censor(body) if body else ''
            item['type_label'] = TYPE_LABELS.get(kind, (kind or 'Post').title())
            item['posted_as'] = meta.get('posted_as')
            item['posted_as_label'] = official
            item['author'] = official
            item['creator_name'] = official
            spec = detail.get(kind)
            item['detail_url'] = (
                safe_url_for(spec[0], '', **{spec[1]: item['id']})
                if spec and item.get('id') else ''
            )
            dt = item.get('sort_dt')
            if dt:
                try:
                    item['formatted_date'] = format_church(dt, '%B %d, %Y')
                    item['formatted_time'] = format_church(dt, '%I:%M %p') if getattr(dt, 'time', None) and dt.time() else ''
                except Exception:
                    item['formatted_date'] = str(dt)[:10]
                    item['formatted_time'] = ''
            out.append(item)
            if len(out) >= limit:
                break
        try:
            from app.models import social as social_model

            voice = 'campus' if wall_campus else 'church'
            viewer_id = session.get('user_id') if has_request_context() else None
            for row in social_model.list_posts_by_voice(voice, wall_campus, limit=limit, viewer_id=viewer_id) or []:
                dt = row.get('created_at')
                kind = row.get('kind') or 'post'
                item = {
                    'id': row.get('id'),
                    'type': kind,
                    'type_label': TYPE_LABELS.get(kind, (kind or 'Post').title()),
                    'title': _censor(row.get('title') or ''),
                    'body': _censor(row.get('body') or '') if row.get('body') else '',
                    'url': row.get('url') or '',
                    'image_url': social_model.identity_url(row.get('image_path')),
                    'when': dt,
                    'sort_dt': dt,
                    'posted_as': voice,
                    'posted_as_label': official,
                    'author': official,
                    'creator_name': official,
                    'author_id': row.get('user_id'),
                    'deletable': True,
                    'visibility': row.get('visibility') or 'public',
                    'shadowed': bool(row.get('shadowed')),
                    'detail_url': '',
                }
                if dt:
                    try:
                        item['formatted_date'] = format_church(dt, '%B %d, %Y')
                        item['formatted_time'] = (
                            format_church(dt, '%I:%M %p')
                            if getattr(dt, 'time', None) and dt.time()
                            else ''
                        )
                    except Exception:
                        item['formatted_date'] = str(dt)[:10]
                        item['formatted_time'] = ''
                out.append(item)
        except Exception as exc:
            print(f'church_wall compose posts: {exc}')
        out.sort(key=lambda x: str(x.get('sort_dt') or x.get('when') or ''), reverse=True)
        viewer_id = session.get('user_id') if has_request_context() else None
        out = visible_items(out, viewer_id, surface='church')[:limit]
        try:
            from app.models.moderation import flag_wall_moderation
            out = flag_wall_moderation(out)
        except Exception:
            pass
        return out
    except Exception:
        return []


def _safe_user_rows(sql: str, user_id: int) -> list[dict]:
    try:
        cur = _cur()
        cur.execute(sql, (int(user_id),))
        return list(cur.fetchall() or [])
    except Exception:
        return []


def member_wall(user_id: int, username: str = '', space: dict | None = None) -> list[dict]:
    """MySpace wall: what they created, plus people they follow. Not the church newspaper."""
    from flask import url_for
    from app.utils.activity_feed import build_member_feed

    uid = int(user_id)
    prayers = _safe_user_rows(
        """
        SELECT id, title, description AS body, date_posted, visibility
        FROM prayers
        WHERE COALESCE(user_id, created_by) = %s
          AND COALESCE(status, 'approved') NOT IN ('rejected', 'deleted', 'removed', 'spam', 'hidden')
        ORDER BY date_posted DESC
        LIMIT 12
        """,
        uid,
    )
    for row in prayers:
        row['poster_username'] = username
    dreams = _safe_user_rows(
        """
        SELECT id, title, description AS body, date_posted, visibility
        FROM dreams WHERE COALESCE(user_id, created_by) = %s
        ORDER BY date_posted DESC LIMIT 12
        """,
        uid,
    )
    prophecies = _safe_user_rows(
        """
        SELECT id, title, description AS body, created_at, visibility
        FROM prophecies WHERE COALESCE(user_id, created_by) = %s
        ORDER BY created_at DESC LIMIT 12
        """,
        uid,
    )
    sermons = _safe_user_rows(
        """
        SELECT id, title, notes AS body, uploaded_at, visibility, external_link
        FROM sermons WHERE COALESCE(uploaded_by, created_by) = %s
        ORDER BY uploaded_at DESC LIMIT 12
        """,
        uid,
    )
    announcements = _safe_user_rows(
        """
        SELECT id, title, content AS body, created_at, visibility
        FROM announcements WHERE created_by = %s
        ORDER BY created_at DESC LIMIT 12
        """,
        uid,
    )
    events = _safe_user_rows(
        """
        SELECT id, event_name AS title, description AS body, event_date, visibility
        FROM events WHERE COALESCE(created_by, updated_by) = %s
        ORDER BY event_date DESC LIMIT 12
        """,
        uid,
    )
    feed = build_member_feed(prayers, dreams, prophecies, sermons, announcements, events)
    try:
        from app.models import social as social_model
        from flask import url_for as _url_for

        for row in social_model.list_posts(user_id, limit=20):
            feed.append({
                'id': row.get('id'),
                'type': row.get('kind') or 'post',
                'type_label': (row.get('kind') or 'post').title(),
                'title': row.get('title'),
                'when': row.get('created_at'),
                'url': row.get('url') or '',
                'image_url': social_model.identity_url(row.get('image_path')),
                'author': username,
                'body': row.get('body') or '',
                'visibility': row.get('visibility') or 'public',
                'author_id': row.get('user_id'),
                'deletable': True,
                'shadowed': bool(row.get('shadowed')),
            })
        if space and space.get('show_training'):
            for row in social_model.list_badges(user_id):
                kind = row.get('badge_kind') or 'started'
                title = row.get('series_title') or 'a study course'
                feed.append({
                    'type': 'badge',
                    'type_label': 'Study',
                    'title': f"{username} {kind} {title}",
                    'when': row.get('created_at'),
                    'url': '',
                    'author': username,
                    'body': '',
                    'visibility': 'public',
                })
    except Exception:
        pass
    if space and space.get('show_replies'):
        for table, parent, label, datecol in (
            ('sermon_comments', 'sermon_id', 'sermon', 'date_added'),
            ('prayers_added', 'prayer_request_id', 'prayer', 'date_added'),
            ('event_comments', 'event_id', 'event', 'created_at'),
            ('announcement_comments', 'announcement_id', 'announcement', 'date_added'),
            ('dream_comments', 'dream_id', 'dream', 'date_posted'),
            ('prophecy_comments', 'prophecy_id', 'prophecy', 'date_added'),
        ):
            try:
                cur = _cur()
                cur.execute(
                    f"""
                    SELECT {parent} AS parent_id, {datecol} AS when_at
                    FROM {table} WHERE user_id=%s
                    ORDER BY {datecol} DESC LIMIT 8
                    """,
                    (uid,),
                )
                for row in cur.fetchall() or []:
                    feed.append({
                        'type': 'comment',
                        'type_label': 'Comment',
                        'title': f"{username} commented on a {label}",
                        'when': row.get('when_at'),
                        'url': '',
                        'author': username,
                        'body': '',
                        'visibility': 'public',
                    })
            except Exception:
                pass
    feed.sort(key=lambda x: str(x.get('when') or ''), reverse=True)
    pairs = [(item.get('type'), item.get('id')) for item in feed]
    mapped = get_postings(pairs)
    personal = []
    for item in feed:
        kind = item.get('type')
        if kind in ('badge', 'comment'):
            personal.append(item)
            continue
        oid = item.get('id')
        meta = infer_posting(kind, oid, mapped.get((kind, int(oid))) if oid else None)
        if meta.get('posted_as') in ('church', 'campus'):
            continue
        item['posted_as'] = 'member'
        personal.append(item)
    feed = personal
    show_follows = True if not space else space.get('show_follows', 1)
    if show_follows:
        try:
            from app.models import social as social_model
            from app.utils.helpers import censor_text as _censor
            from app.utils.time_utils import format_church
            from flask import has_request_context, session as flask_session

            viewer_id = flask_session.get('user_id') if has_request_context() else None
            followed = social_model.following_ids(uid)
            seen = {(i.get('type'), i.get('id')) for i in feed}
            for row in social_model.list_posts_by_users(followed, viewer_id=viewer_id, limit=20):
                key = (row.get('kind') or 'post', row.get('id'))
                if key in seen:
                    continue
                seen.add(key)
                dt = row.get('created_at')
                name = row.get('display_name') or row.get('username') or 'Member'
                item = {
                    'id': row.get('id'),
                    'type': row.get('kind') or 'post',
                    'type_label': TYPE_LABELS.get(row.get('kind') or 'post', 'Post'),
                    'title': _censor(row.get('title') or ''),
                    'body': _censor(row.get('body') or '') if row.get('body') else '',
                    'url': row.get('url') or '',
                    'image_url': row.get('image_url') or '',
                    'when': dt,
                    'sort_dt': dt,
                    'author': name,
                    'creator_name': name,
                    'author_id': row.get('user_id'),
                    'author_url': row.get('author_url') or '',
                    'from_follow': True,
                    'deletable': False,
                    'visibility': row.get('visibility') or 'public',
                    'shadowed': bool(row.get('shadowed')),
                }
                if dt:
                    try:
                        item['formatted_date'] = format_church(dt, '%B %d, %Y')
                        item['formatted_time'] = (
                            format_church(dt, '%I:%M %p')
                            if getattr(dt, 'time', None) and dt.time()
                            else ''
                        )
                    except Exception:
                        item['formatted_date'] = str(dt)[:10]
                        item['formatted_time'] = ''
                feed.append(item)
        except Exception as exc:
            print(f'member_wall follows: {exc}')
    feed.sort(key=lambda x: str(x.get('when') or x.get('sort_dt') or ''), reverse=True)
    try:
        from app.routes.public.public_dashboard.queries import get_recent_comments
        for item in feed:
            kind = item.get('type')
            oid = item.get('id')
            if oid and kind in ('prayer', 'announcement', 'event', 'sermon', 'dream', 'prophecy'):
                item['comments'] = get_recent_comments(kind, oid, limit=4)
    except Exception:
        pass
    from app.utils.helpers import censor_text as _censor_all
    for item in feed:
        item['type_label'] = TYPE_LABELS.get(item.get('type'), item.get('type_label') or (item.get('type') or 'Post').title())
        item['title'] = _censor_all(item.get('title') or '')
        item['body'] = _censor_all(item.get('body') or '') if item.get('body') else ''
    try:
        from app.models.moderation import flag_wall_moderation
        feed = flag_wall_moderation(feed)
    except Exception:
        pass
    return feed[:40]


def media_access(owner_type: str, owner_id: int, viewer_id: int | None = None) -> str:
    """Empty string if the viewer may see this page's photos. Else login/private/missing."""
    kind = (owner_type or '').strip()
    if kind != 'member':
        return ''
    space = get_member_space(int(owner_id)) or {}
    is_owner = bool(viewer_id and int(viewer_id) == int(owner_id))
    if not space and not is_owner:
        return 'missing'
    if space.get('page_private') and not is_owner:
        return 'private'
    if space and not space.get('show_to_visitors') and not viewer_id and not is_owner:
        return 'login'
    if viewer_id and not is_owner:
        try:
            from app.models import social as social_model
            if social_model.blocked_either_way(viewer_id, int(owner_id)):
                return 'missing'
        except Exception:
            pass
    return ''


def find_people(query: str = '', viewer_id: int | None = None, limit: int = 40) -> list[dict]:
    """Any church member can search people across branches. Private / opted-out pages stay hidden."""
    q = (query or '').strip()
    home_id = 0
    if viewer_id and not single_church_install():
        try:
            from app.models import campuses as campus_model
            home_id = int(campus_model.user_home_campus_id(int(viewer_id)) or 0)
        except Exception:
            home_id = 0
    try:
        from app.models import social as social_model
        cur = _cur()
        sql = """
            SELECT u.id, u.username, u.first_name, u.last_name, u.role,
                   u.primary_campus_id,
                   m.photo_path, m.hometown, m.occupation, m.show_to_visitors,
                   m.user_id AS has_space,
                   COALESCE(c.short_name, c.name) AS branch_name
            FROM users u
            LEFT JOIN member_spaces m ON m.user_id = u.id
            LEFT JOIN campuses c ON c.id = u.primary_campus_id
            WHERE (
                m.user_id IS NULL
                OR (
                    COALESCE(m.page_private, 0) = 0
                    AND COALESCE(m.show_in_directory, 1) = 1
                )
            )
        """
        args: list = []
        if not viewer_id:
            sql += " AND COALESCE(m.show_to_visitors, 0) = 1 AND m.user_id IS NOT NULL"
        if q:
            like = f"%{q}%"
            sql += """
              AND (
                u.username LIKE %s
                OR u.first_name LIKE %s
                OR u.last_name LIKE %s
                OR CONCAT(u.first_name, ' ', u.last_name) LIKE %s
              )
            """
            args.extend([like, like, like, like])
        if home_id:
            sql += " ORDER BY (u.primary_campus_id = %s) DESC, u.first_name ASC, u.last_name ASC LIMIT %s"
            args.extend([home_id, int(limit)])
        else:
            sql += " ORDER BY u.first_name ASC, u.last_name ASC LIMIT %s"
            args.append(int(limit))
        cur.execute(sql, args)
        rows = list(cur.fetchall() or [])
    except Exception as exc:
        print(f'find_people: {exc}')
        return []
    out = []
    for row in rows:
        uid = int(row.get('id') or 0)
        if viewer_id and uid == int(viewer_id):
            continue
        if viewer_id and social_model.blocked_either_way(viewer_id, uid):
            continue
        name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
        has_page = bool(row.get('has_space'))
        out.append({
            **row,
            'display_name': name or row.get('username') or 'Member',
            'has_page': has_page,
            'page_url': f"/church/u/{row.get('username')}" if row.get('username') else '',
            'pic_url': social_model.identity_url(row.get('photo_path')) if has_page else '',
            'same_branch': bool(home_id and int(row.get('primary_campus_id') or 0) == home_id),
        })
    return out


def staff_on_page(campus: Optional[dict] = None) -> list[dict]:
    """Pastors / leads with a member page, for the church profile strip."""
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT u.id, u.username, u.first_name, u.last_name, u.role,
                   u.primary_campus_id
            FROM users u
            INNER JOIN member_spaces m ON m.user_id = u.id
            WHERE u.role IN ('Owner', 'Admin')
            ORDER BY u.role = 'Owner' DESC, u.first_name ASC
            LIMIT 8
            """
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        rows = []
    out = []
    for row in rows:
        name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
        out.append({
            **row,
            'display_name': name or row.get('username'),
            'page_url': f"/church/u/{row.get('username')}",
        })
    pastor = (campus or {}).get('pastor_name') or ''
    if pastor and not any(
        pastor.lower() in (p.get('display_name') or '').lower() for p in out
    ):
        out.insert(0, {
            'display_name': pastor,
            'role': 'Pastor',
            'username': '',
            'page_url': '',
        })
    return out


def hero_for_profile() -> str:
    try:
        from app.utils.appearance import list_hero_images
        images = list_hero_images('welcome') or list_hero_images('login') or []
        if images:
            return images[0].get('url') or ''
    except Exception:
        pass
    settings = getattr(g, 'settings', None) or {} if has_request_context() else {}
    logo = (settings.get('logo_path') or settings.get('icon_path') or '').strip()
    if not logo:
        return ''
    if logo.startswith('http') or logo.startswith('/'):
        return logo
    return '/static/images/' + logo.lstrip('/')
