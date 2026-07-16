# Communications: mass email/SMS campaigns, audiences, workflows, drip runner.

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, Optional

import pymysql
import requests

from app.models.db import get_db
from app.utils.field_crypto import encrypt, decrypt
from app.utils.time_utils import now_church, utc_now


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


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
    return json.dumps(val, ensure_ascii=False)


# ── Settings / SMS provider ─────────────────────────────────────────────────

def get_sms_settings() -> dict:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT sms_enabled, sms_provider, sms_account_sid, sms_auth_token_enc,
                   sms_from_number, sms_test_mode, church_name, comm_default_from_name
            FROM settings WHERE id = 1
            """
        )
        row = cur.fetchone() or {}
    except Exception:
        row = {}
    return {
        'enabled': bool(row.get('sms_enabled')),
        'provider': row.get('sms_provider') or 'twilio',
        'account_sid': (row.get('sms_account_sid') or '').strip(),
        'has_token': bool(row.get('sms_auth_token_enc')),
        'from_number': (row.get('sms_from_number') or '').strip(),
        'test_mode': bool(row.get('sms_test_mode', 1)),
        'church_name': row.get('church_name') or 'Church',
        'from_name': row.get('comm_default_from_name') or row.get('church_name') or 'Church',
    }


def save_sms_settings(data: dict) -> None:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT sms_auth_token_enc FROM settings WHERE id = 1")
    existing = cur.fetchone() or {}
    token = (data.get('auth_token') or '').strip()
    enc = encrypt(token) if token else existing.get('sms_auth_token_enc')
    cur.execute(
        """
        UPDATE settings SET
            sms_enabled = %s,
            sms_provider = %s,
            sms_account_sid = %s,
            sms_auth_token_enc = %s,
            sms_from_number = %s,
            sms_test_mode = %s,
            comm_default_from_name = %s
        WHERE id = 1
        """,
        (
            1 if data.get('enabled') else 0,
            (data.get('provider') or 'twilio')[:32],
            (data.get('account_sid') or '').strip()[:128] or None,
            enc,
            (data.get('from_number') or '').strip()[:40] or None,
            1 if data.get('test_mode', True) else 0,
            (data.get('from_name') or '').strip()[:120] or None,
        ),
    )
    db.commit()


def _sms_token() -> str:
    cur = _cur()
    cur.execute("SELECT sms_auth_token_enc FROM settings WHERE id = 1")
    row = cur.fetchone() or {}
    raw = row.get('sms_auth_token_enc')
    return decrypt(raw) if raw else ''


def normalize_phone(phone: str) -> str:
    """Keep digits and leading + for E.164-ish numbers."""
    if not phone:
        return ''
    p = phone.strip()
    if p.startswith('+'):
        digits = re.sub(r'\D', '', p[1:])
        return f'+{digits}' if digits else ''
    digits = re.sub(r'\D', '', p)
    if len(digits) == 10:
        return f'+1{digits}'  # US default
    if len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    return f'+{digits}' if digits else ''


def send_sms(to_phone: str, body: str) -> dict:
    """
    Send SMS via Twilio REST API (or test-mode log).
    Returns {ok, status, error, test_mode}.
    """
    settings = get_sms_settings()
    to_n = normalize_phone(to_phone)
    if not to_n:
        return {'ok': False, 'status': 'failed', 'error': 'Invalid phone', 'test_mode': False}
    if not settings['enabled'] and not settings['test_mode']:
        return {'ok': False, 'status': 'failed', 'error': 'SMS disabled', 'test_mode': False}

    if settings['test_mode'] or not settings['enabled']:
        # Dry-run — always succeed for testing workflows without Twilio
        return {
            'ok': True,
            'status': 'test_sent',
            'error': None,
            'test_mode': True,
            'to': to_n,
            'body_preview': (body or '')[:160],
        }

    sid = settings['account_sid']
    token = _sms_token()
    from_n = settings['from_number']
    if not sid or not token or not from_n:
        return {'ok': False, 'status': 'failed', 'error': 'SMS provider not configured', 'test_mode': False}

    url = f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'
    try:
        resp = requests.post(
            url,
            data={'To': to_n, 'From': from_n, 'Body': body[:1600]},
            auth=(sid, token),
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return {'ok': True, 'status': 'sent', 'error': None, 'test_mode': False}
        err = resp.text[:300]
        return {'ok': False, 'status': 'failed', 'error': err, 'test_mode': False}
    except Exception as e:
        return {'ok': False, 'status': 'failed', 'error': str(e)[:300], 'test_mode': False}


def send_email_message(to_email: str, subject: str, body: str) -> dict:
    try:
        from app.utils.emailer import send_email
        send_email(to_email, subject, body)
        return {'ok': True, 'status': 'sent', 'error': None}
    except Exception as e:
        return {'ok': False, 'status': 'failed', 'error': str(e)[:300]}


# Trigger catalog — paid-platform style automation
TRIGGER_TYPES = [
    ('manual', 'Manual enrollment only'),
    ('new_visitor', 'New visitor / pending registration'),
    ('new_member', 'New approved member'),
    ('prayer_request', 'Prayer request submitted'),
    ('volunteer_onboarding', 'Joined a volunteer team'),
    ('giving_lapsed', 'Giving reminder (no gift in N days)'),
    ('follow_up', 'Pastoral care / follow-up open'),
]

TRIGGER_LABELS = {k: v for k, v in TRIGGER_TYPES}

# Step channels: messaging + side-effect actions
STEP_CHANNELS = [
    ('email', 'Email'),
    ('sms', 'SMS'),
    ('care_task', 'Create pastoral care task'),
    ('notify_pastoral', 'Notify pastoral team (email)'),
]


def personalize(template: str, user: dict, church_name: str = '', context: dict | None = None) -> str:
    if not template:
        return ''
    mapping = {
        'first_name': (user.get('first_name') or 'Friend').strip(),
        'last_name': (user.get('last_name') or '').strip(),
        'full_name': f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip() or 'Friend',
        'email': (user.get('email') or '').strip(),
        'phone': (user.get('phone') or '').strip(),
        'username': (user.get('username') or '').strip(),
        'church_name': church_name or 'Church',
    }
    if context:
        for key, val in context.items():
            if val is None:
                continue
            mapping[str(key)] = str(val)
    out = template
    for key, val in mapping.items():
        out = out.replace('{{' + key + '}}', val)
        out = out.replace('{' + key + '}', val)
    return out


def parse_trigger_config(wf: dict | None) -> dict:
    if not wf:
        return {}
    raw = wf.get('trigger_config_json') if isinstance(wf, dict) else None
    data = _loads(raw, {})
    return data if isinstance(data, dict) else {}


# ── Audiences ───────────────────────────────────────────────────────────────

AUDIENCE_TYPES = [
    ('all_opt_in', 'All members who opt in'),
    ('all_with_contact', 'All approved members with email/phone (ignore opt-in)'),
    ('role', 'By role'),
    ('group', 'By group'),
    ('selected', 'Selected members'),
    ('newsletter', 'Newsletter opt-in only'),
]


def resolve_audience(
    channel: str,
    audience_type: str,
    *,
    audience_ref: str | None = None,
    audience_ids: list | None = None,
) -> list[dict]:
    """
    Return list of {user_id, first_name, last_name, email, phone, address}.
    channel: email | sms
    """
    cur = _cur()
    channel = (channel or 'email').lower()
    base = """
        SELECT u.id AS user_id, u.first_name, u.last_name, u.email, u.phone, u.username, u.role
        FROM users u
        WHERE COALESCE(u.needs_approval, 0) = 0
          AND COALESCE(u.is_shadow_banned, 0) = 0
    """
    params: list[Any] = []

    if audience_type == 'role' and audience_ref:
        base += " AND u.role = %s"
        params.append(audience_ref)
    elif audience_type == 'group' and audience_ref:
        base += """
            AND EXISTS (
                SELECT 1 FROM user_groups ug WHERE ug.user_id = u.id AND ug.group_id = %s
            )
        """
        params.append(int(audience_ref))
    elif audience_type == 'selected' and audience_ids:
        ids = [int(x) for x in audience_ids if str(x).isdigit() or isinstance(x, int)]
        if not ids:
            return []
        placeholders = ','.join(['%s'] * len(ids))
        base += f" AND u.id IN ({placeholders})"
        params.extend(ids)
    elif audience_type == 'newsletter':
        base += " AND COALESCE(u.accepts_newsletter_emails, 1) = 1 AND COALESCE(u.accepts_emails, 1) = 1"

    # Contact + opt-in filters
    if channel == 'sms':
        base += " AND u.phone IS NOT NULL AND TRIM(u.phone) != ''"
        if audience_type not in ('all_with_contact', 'selected'):
            base += " AND COALESCE(u.accepts_sms, 0) = 1"
    else:
        base += " AND u.email IS NOT NULL AND TRIM(u.email) != ''"
        if audience_type == 'all_opt_in' or audience_type in ('role', 'group', 'newsletter'):
            base += """
                AND COALESCE(u.accepts_emails, 1) = 1
                AND COALESCE(u.accepts_mass_emails, 1) = 1
            """
        # all_with_contact / selected: still require email but allow override for staff selected

    base += " ORDER BY u.last_name, u.first_name"
    cur.execute(base, params)
    rows = list(cur.fetchall() or [])
    out = []
    for r in rows:
        if channel == 'sms':
            addr = normalize_phone(r.get('phone') or '')
            if not addr:
                continue
        else:
            addr = (r.get('email') or '').strip()
            if not addr or '@' not in addr:
                continue
        r['address'] = addr
        r['display_name'] = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip()
        out.append(r)
    return out


def preview_audience_count(channel, audience_type, audience_ref=None, audience_ids=None) -> int:
    return len(resolve_audience(channel, audience_type, audience_ref=audience_ref, audience_ids=audience_ids))


def list_groups_simple() -> list[dict]:
    cur = _cur()
    cur.execute("SELECT id, name FROM groups ORDER BY name")
    return list(cur.fetchall() or [])


def list_members_for_picker(limit=500) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT id, first_name, last_name, email, phone
        FROM users
        WHERE COALESCE(needs_approval,0)=0 AND COALESCE(is_shadow_banned,0)=0
        ORDER BY last_name, first_name
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall() or [])


# ── Campaigns ───────────────────────────────────────────────────────────────

def list_campaigns(limit=50) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT * FROM comm_campaigns
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall() or [])


def get_campaign(campaign_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM comm_campaigns WHERE id = %s", (campaign_id,))
    row = cur.fetchone()
    if row:
        row['audience_ids'] = _loads(row.get('audience_ids_json'), [])
    return row


def create_campaign(data: dict, created_by: int | None) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO comm_campaigns
            (channel, title, subject, body, audience_type, audience_ref, audience_ids_json,
             status, scheduled_at, created_by, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            (data.get('channel') or 'email').lower(),
            (data.get('title') or 'Untitled campaign').strip()[:255],
            (data.get('subject') or '').strip()[:500] or None,
            data.get('body') or '',
            data.get('audience_type') or 'all_opt_in',
            data.get('audience_ref') or None,
            _dumps(data.get('audience_ids') or []),
            data.get('status') or 'draft',
            data.get('scheduled_at') or None,
            created_by,
            (data.get('notes') or '').strip()[:500] or None,
        ),
    )
    db.commit()
    return cur.lastrowid


def update_campaign(campaign_id: int, data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    fields, vals = [], []
    mapping = {
        'title': lambda v: (v or '').strip()[:255],
        'subject': lambda v: (v or '').strip()[:500] or None,
        'body': lambda v: v or '',
        'channel': lambda v: (v or 'email').lower(),
        'audience_type': lambda v: v or 'all_opt_in',
        'audience_ref': lambda v: v or None,
        'status': lambda v: v,
        'scheduled_at': lambda v: v or None,
        'notes': lambda v: (v or '').strip()[:500] or None,
    }
    for k, fn in mapping.items():
        if k in data:
            fields.append(f'{k}=%s')
            vals.append(fn(data[k]))
    if 'audience_ids' in data:
        fields.append('audience_ids_json=%s')
        vals.append(_dumps(data.get('audience_ids') or []))
    if not fields:
        return
    vals.append(campaign_id)
    cur.execute(f"UPDATE comm_campaigns SET {', '.join(fields)} WHERE id=%s", vals)
    db.commit()


def delete_campaign(campaign_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM comm_campaigns WHERE id=%s AND status IN ('draft','cancelled')", (campaign_id,))
    db.commit()


def _log_message(**kwargs):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO comm_message_log
            (channel, source, campaign_id, workflow_id, enrollment_id, user_id,
             to_address, subject, body_preview, status, error_detail, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            kwargs.get('channel'),
            kwargs.get('source') or 'campaign',
            kwargs.get('campaign_id'),
            kwargs.get('workflow_id'),
            kwargs.get('enrollment_id'),
            kwargs.get('user_id'),
            kwargs.get('to_address'),
            kwargs.get('subject'),
            (kwargs.get('body') or '')[:500],
            kwargs.get('status'),
            kwargs.get('error'),
            kwargs.get('created_by'),
        ),
    )
    db.commit()


def prepare_and_send_campaign(campaign_id: int, *, force: bool = False) -> dict:
    """Resolve audience, send all messages, update stats. Returns summary dict."""
    camp = get_campaign(campaign_id)
    if not camp:
        raise ValueError('Campaign not found')
    if camp['status'] in ('sent', 'sending') and not force:
        raise ValueError(f"Campaign already {camp['status']}")
    if camp['status'] == 'scheduled' and camp.get('scheduled_at') and not force:
        # Only send if due
        sched = camp['scheduled_at']
        if isinstance(sched, str):
            pass
        else:
            from datetime import timezone
            now = utc_now()
            if getattr(sched, 'tzinfo', None) is None:
                sched = sched.replace(tzinfo=timezone.utc) if hasattr(sched, 'replace') else sched
            try:
                if now < sched:
                    return {'ok': False, 'deferred': True, 'message': 'Not due yet'}
            except TypeError:
                pass

    channel = (camp['channel'] or 'email').lower()
    recipients = resolve_audience(
        channel,
        camp['audience_type'],
        audience_ref=camp.get('audience_ref'),
        audience_ids=camp.get('audience_ids') or _loads(camp.get('audience_ids_json'), []),
    )
    settings = get_sms_settings()
    church = settings.get('church_name') or 'Church'

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE comm_campaigns SET status='sending', started_at=%s, total_recipients=%s WHERE id=%s",
        (utc_now(), len(recipients), campaign_id),
    )
    # Clear old recipient rows if re-send
    cur.execute("DELETE FROM comm_campaign_recipients WHERE campaign_id=%s", (campaign_id,))
    db.commit()

    sent = failed = skipped = 0
    for r in recipients:
        user = r
        subject = personalize(camp.get('subject') or '', user, church) if channel == 'email' else None
        body = personalize(camp.get('body') or '', user, church)
        if channel == 'email':
            footer = f"\n\n— {church}\n(You receive this because you opted in to church communications. Update preferences in your profile.)"
            body = body + footer
            result = send_email_message(r['address'], subject or camp.get('title') or 'Message', body)
        else:
            result = send_sms(r['address'], body)

        status = result.get('status') or ('sent' if result.get('ok') else 'failed')
        if result.get('ok'):
            sent += 1
        else:
            failed += 1

        cur.execute(
            """
            INSERT INTO comm_campaign_recipients
                (campaign_id, user_id, address, display_name, status, error_detail, sent_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                campaign_id,
                r.get('user_id'),
                r['address'],
                r.get('display_name'),
                status,
                result.get('error'),
                utc_now() if result.get('ok') else None,
            ),
        )
        _log_message(
            channel=channel,
            source='campaign',
            campaign_id=campaign_id,
            user_id=r.get('user_id'),
            to_address=r['address'],
            subject=subject,
            body=body,
            status=status,
            error=result.get('error'),
            created_by=camp.get('created_by'),
        )
    db.commit()

    cur.execute(
        """
        UPDATE comm_campaigns SET
            status='sent', completed_at=%s, sent_count=%s, failed_count=%s, skipped_count=%s
        WHERE id=%s
        """,
        (utc_now(), sent, failed, skipped, campaign_id),
    )
    db.commit()
    return {'ok': True, 'sent': sent, 'failed': failed, 'total': len(recipients)}


def process_due_campaigns() -> int:
    """Send scheduled campaigns that are due. Returns count processed."""
    cur = _cur()
    cur.execute(
        """
        SELECT id FROM comm_campaigns
        WHERE status = 'scheduled'
          AND scheduled_at IS NOT NULL
          AND scheduled_at <= %s
        ORDER BY scheduled_at ASC
        LIMIT 20
        """,
        (utc_now(),),
    )
    rows = cur.fetchall() or []
    n = 0
    for r in rows:
        try:
            prepare_and_send_campaign(int(r['id']), force=True)
            n += 1
        except Exception as e:
            print(f"Scheduled campaign {r['id']} failed: {e}")
    return n


# ── Workflows / drips ───────────────────────────────────────────────────────

def list_workflows() -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT w.*,
               (SELECT COUNT(*) FROM comm_workflow_steps s WHERE s.workflow_id = w.id) AS step_count,
               (SELECT COUNT(*) FROM comm_workflow_enrollments e
                 WHERE e.workflow_id = w.id AND e.status = 'active') AS active_enrollments
        FROM comm_workflows w
        ORDER BY w.updated_at DESC
        """
    )
    return list(cur.fetchall() or [])


def get_workflow(workflow_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM comm_workflows WHERE id = %s", (workflow_id,))
    return cur.fetchone()


def create_workflow(data: dict, created_by: int | None) -> int:
    db = get_db()
    cur = db.cursor()
    cfg = data.get('trigger_config')
    if cfg is not None and not isinstance(cfg, str):
        cfg = _dumps(cfg)
    elif data.get('trigger_config_json') is not None:
        cfg = data.get('trigger_config_json')
    else:
        cfg = None
    cur.execute(
        """
        INSERT INTO comm_workflows (name, description, trigger_type, trigger_config_json, status, created_by)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            (data.get('name') or 'New workflow').strip()[:255],
            (data.get('description') or '').strip() or None,
            data.get('trigger_type') or 'manual',
            cfg,
            data.get('status') or 'draft',
            created_by,
        ),
    )
    db.commit()
    return cur.lastrowid


def update_workflow(workflow_id: int, data: dict) -> None:
    db = get_db()
    cur = db.cursor()
    fields, vals = [], []
    for key in ('name', 'description', 'trigger_type', 'status', 'trigger_config_json'):
        if key not in data:
            continue
        fields.append(f'{key}=%s')
        val = data[key]
        if key == 'name':
            val = (val or '').strip()[:255]
        elif key == 'description':
            val = (val or '').strip() or None
        elif key == 'trigger_config_json' and not isinstance(val, str) and val is not None:
            val = _dumps(val)
        vals.append(val)
    if 'trigger_config' in data and 'trigger_config_json' not in data:
        fields.append('trigger_config_json=%s')
        cfg = data['trigger_config']
        vals.append(_dumps(cfg) if cfg is not None and not isinstance(cfg, str) else cfg)
    if not fields:
        return
    vals.append(workflow_id)
    cur.execute(f"UPDATE comm_workflows SET {', '.join(fields)} WHERE id=%s", vals)
    db.commit()


def list_steps(workflow_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        "SELECT * FROM comm_workflow_steps WHERE workflow_id=%s ORDER BY step_order ASC, id ASC",
        (workflow_id,),
    )
    return list(cur.fetchall() or [])


def save_step(workflow_id: int, data: dict, step_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    if step_id:
        cur.execute(
            """
            UPDATE comm_workflow_steps SET
                step_order=%s, delay_days=%s, channel=%s, subject=%s, body=%s
            WHERE id=%s AND workflow_id=%s
            """,
            (
                int(data.get('step_order') or 0),
                int(data.get('delay_days') or 0),
                (data.get('channel') or 'email').lower(),
                (data.get('subject') or '').strip()[:500] or None,
                data.get('body') or '',
                step_id,
                workflow_id,
            ),
        )
        db.commit()
        return step_id
    # next order (cursor may be DictCursor depending on get_db defaults)
    cur.execute(
        "SELECT COALESCE(MAX(step_order),-1)+1 AS nxt FROM comm_workflow_steps WHERE workflow_id=%s",
        (workflow_id,),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        nxt = int(row.get('nxt') or 0)
    else:
        nxt = int(row[0] if row else 0)
    cur.execute(
        """
        INSERT INTO comm_workflow_steps (workflow_id, step_order, delay_days, channel, subject, body)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            workflow_id,
            int(data.get('step_order') if data.get('step_order') is not None else nxt),
            int(data.get('delay_days') or 0),
            (data.get('channel') or 'email').lower(),
            (data.get('subject') or '').strip()[:500] or None,
            data.get('body') or '',
        ),
    )
    db.commit()
    return cur.lastrowid


def delete_step(step_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM comm_workflow_steps WHERE id=%s", (step_id,))
    db.commit()


def enroll_user(workflow_id: int, user_id: int, context: dict | None = None) -> int:
    wf = get_workflow(workflow_id)
    if not wf:
        raise ValueError('Workflow not found')
    steps = list_steps(workflow_id)
    if not steps:
        raise ValueError('Add at least one step before enrolling people.')
    delay = int(steps[0].get('delay_days') or 0)
    next_run = utc_now() + timedelta(days=delay) if delay else utc_now()
    ctx_json = _dumps(context) if context else None
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO comm_workflow_enrollments
            (workflow_id, user_id, status, current_step, next_run_at, context_json)
        VALUES (%s,%s,'active',0,%s,%s)
        ON DUPLICATE KEY UPDATE
            status='active', current_step=0, next_run_at=VALUES(next_run_at),
            completed_at=NULL, last_error=NULL,
            context_json=COALESCE(VALUES(context_json), context_json)
        """,
        (workflow_id, user_id, next_run, ctx_json),
    )
    db.commit()
    return cur.lastrowid


def enroll_audience(workflow_id: int, audience_type: str, audience_ref=None, audience_ids=None) -> int:
    # Prefer email audience for enrollments; SMS-only users still get enrolled if they have user id
    people = resolve_audience('email', audience_type, audience_ref=audience_ref, audience_ids=audience_ids)
    if not people:
        people = resolve_audience('sms', audience_type, audience_ref=audience_ref, audience_ids=audience_ids)
    n = 0
    for p in people:
        try:
            enroll_user(workflow_id, int(p['user_id']))
            n += 1
        except Exception:
            continue
    return n


def process_due_enrollments(limit: int = 50) -> int:
    """Run due drip steps. Returns number of messages attempted."""
    cur = _cur()
    cur.execute(
        """
        SELECT e.*, w.status AS workflow_status, w.name AS workflow_name
        FROM comm_workflow_enrollments e
        JOIN comm_workflows w ON w.id = e.workflow_id
        WHERE e.status = 'active'
          AND w.status = 'active'
          AND e.next_run_at IS NOT NULL
          AND e.next_run_at <= %s
        ORDER BY e.next_run_at ASC
        LIMIT %s
        """,
        (utc_now(), limit),
    )
    enrollments = list(cur.fetchall() or [])
    attempted = 0
    settings = get_sms_settings()
    church = settings.get('church_name') or 'Church'

    for en in enrollments:
        steps = list_steps(en['workflow_id'])
        step_idx = int(en.get('current_step') or 0)
        if step_idx >= len(steps):
            _complete_enrollment(en['id'])
            continue
        step = steps[step_idx]
        user = _get_user(en['user_id'])
        if not user:
            _fail_enrollment(en['id'], 'User not found')
            continue

        context = _loads(en.get('context_json'), {}) or {}
        channel = (step.get('channel') or 'email').lower()
        subject = personalize(step.get('subject') or '', user, church, context)
        body = personalize(step.get('body') or '', user, church, context)

        if channel == 'care_task':
            result = _action_create_care_task(user, subject, body, context)
            addr = f"care:{user.get('user_id')}"
        elif channel == 'notify_pastoral':
            result = _action_notify_pastoral(user, subject, body, church)
            addr = 'pastoral_team'
        elif channel == 'sms':
            addr = normalize_phone(user.get('phone') or '')
            if not addr or not user.get('accepts_sms', 0):
                _advance_enrollment(en, steps, step_idx, skip=True)
                continue
            result = send_sms(addr, body)
        else:
            addr = (user.get('email') or '').strip()
            if not addr or not user.get('accepts_emails', 1):
                _advance_enrollment(en, steps, step_idx, skip=True)
                continue
            body = body + f"\n\n— {church}"
            result = send_email_message(addr, subject or step.get('subject') or 'Update', body)

        attempted += 1
        _log_message(
            channel=channel,
            source='workflow',
            workflow_id=en['workflow_id'],
            enrollment_id=en['id'],
            user_id=en['user_id'],
            to_address=addr,
            subject=subject,
            body=body,
            status=result.get('status'),
            error=result.get('error'),
        )
        if result.get('ok'):
            _advance_enrollment(en, steps, step_idx, skip=False)
        else:
            db = get_db()
            c2 = db.cursor()
            c2.execute(
                "UPDATE comm_workflow_enrollments SET last_error=%s WHERE id=%s",
                ((result.get('error') or 'send failed')[:500], en['id']),
            )
            db.commit()
            _advance_enrollment(en, steps, step_idx, skip=False)

    return attempted


def _action_create_care_task(user: dict, subject: str, body: str, context: dict) -> dict:
    """Open a pastoral care request for the enrolled person (follow-up automation)."""
    try:
        from app.models.pastoral.care import create_care_request
        uid = int(user.get('user_id') or 0)
        if not uid:
            return {'ok': False, 'status': 'failed', 'error': 'No user for care task'}
        title = (subject or context.get('title') or 'Automated follow-up').strip()[:200]
        desc = (body or 'Created by automation workflow.').strip()
        if context.get('prayer_title'):
            desc = f"Related prayer: {context.get('prayer_title')}\n\n{desc}"
        create_care_request(
            {
                'member_id': uid,
                'request_type': context.get('care_type') or 'follow_up',
                'title': title,
                'description': desc,
                'urgency': context.get('urgency') or 'normal',
                'status': 'open',
            },
            created_by=uid,
        )
        return {'ok': True, 'status': 'care_created', 'error': None}
    except Exception as e:
        return {'ok': False, 'status': 'failed', 'error': str(e)[:300]}


def _action_notify_pastoral(user: dict, subject: str, body: str, church: str) -> dict:
    """Email everyone in the Pastoral Group about this automation event."""
    try:
        from app.models.pastoral.shared import get_pastoral_team_members
        team = get_pastoral_team_members() or []
        if not team:
            return {'ok': False, 'status': 'failed', 'error': 'No pastoral team members'}
        who = f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip() or 'Someone'
        subj = subject or f'[{church}] Automation alert'
        msg = (
            f"{body or 'An automation workflow needs pastoral attention.'}\n\n"
            f"Person: {who}\n"
            f"Email: {user.get('email') or '—'}\n"
            f"Phone: {user.get('phone') or '—'}\n"
        )
        sent = 0
        for m in team:
            email = (m.get('email') or '').strip()
            if not email:
                continue
            r = send_email_message(email, subj, msg)
            if r.get('ok'):
                sent += 1
        if sent:
            return {'ok': True, 'status': 'notified', 'error': None}
        return {'ok': False, 'status': 'failed', 'error': 'No pastoral emails sent'}
    except Exception as e:
        return {'ok': False, 'status': 'failed', 'error': str(e)[:300]}


def _get_user(user_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT id AS user_id, first_name, last_name, email, phone, username,
               accepts_emails, accepts_sms, accepts_mass_emails
        FROM users WHERE id = %s
        """,
        (user_id,),
    )
    return cur.fetchone()


def _advance_enrollment(en: dict, steps: list, step_idx: int, skip: bool = False):
    db = get_db()
    cur = db.cursor()
    next_idx = step_idx + 1
    if next_idx >= len(steps):
        cur.execute(
            """
            UPDATE comm_workflow_enrollments
            SET status='completed', current_step=%s, completed_at=%s, next_run_at=NULL
            WHERE id=%s
            """,
            (next_idx, utc_now(), en['id']),
        )
    else:
        delay = int(steps[next_idx].get('delay_days') or 0)
        next_run = utc_now() + timedelta(days=delay) if delay else utc_now()
        cur.execute(
            """
            UPDATE comm_workflow_enrollments
            SET current_step=%s, next_run_at=%s
            WHERE id=%s
            """,
            (next_idx, next_run, en['id']),
        )
    db.commit()


def _complete_enrollment(enrollment_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE comm_workflow_enrollments SET status='completed', completed_at=%s, next_run_at=NULL WHERE id=%s",
        (utc_now(), enrollment_id),
    )
    db.commit()


def _fail_enrollment(enrollment_id: int, error: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE comm_workflow_enrollments SET status='failed', last_error=%s WHERE id=%s",
        (error[:500], enrollment_id),
    )
    db.commit()


def _active_workflows(trigger_type: str) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT * FROM comm_workflows
        WHERE status = 'active' AND trigger_type = %s
        """,
        (trigger_type,),
    )
    return list(cur.fetchall() or [])


def _already_enrolled(workflow_id: int, user_id: int) -> bool:
    cur = _cur()
    cur.execute(
        "SELECT id FROM comm_workflow_enrollments WHERE workflow_id=%s AND user_id=%s",
        (workflow_id, user_id),
    )
    return cur.fetchone() is not None


def fire_trigger(trigger_type: str, user_id: int, context: dict | None = None) -> int:
    """
    Instant automation: enroll user_id into every active workflow of this trigger type.
    Returns number of new enrollments.
    """
    if not user_id or not trigger_type:
        return 0
    n = 0
    for wf in _active_workflows(trigger_type):
        try:
            if _already_enrolled(wf['id'], user_id):
                # Allow re-fire for prayer/follow_up by restarting enrollment
                if trigger_type in ('prayer_request', 'follow_up', 'volunteer_onboarding'):
                    enroll_user(wf['id'], user_id, context=context)
                    n += 1
                continue
            enroll_user(wf['id'], user_id, context=context)
            n += 1
        except Exception as e:
            print(f"fire_trigger {trigger_type} wf={wf.get('id')} user={user_id}: {e}")
    return n


def auto_enroll_new_members(since_hours: int = 72) -> int:
    """Enroll recent approved members into active new_member workflows."""
    cur = _cur()
    workflows = _active_workflows('new_member')
    if not workflows:
        return 0
    cur.execute(
        """
        SELECT id FROM users
        WHERE COALESCE(needs_approval,0)=0
          AND COALESCE(is_shadow_banned,0)=0
          AND role NOT IN ('pending','banned')
          AND created_at >= (UTC_TIMESTAMP() - INTERVAL %s HOUR)
        """,
        (since_hours,),
    )
    users = cur.fetchall() or []
    n = 0
    for wf in workflows:
        for u in users:
            try:
                if _already_enrolled(wf['id'], u['id']):
                    continue
                enroll_user(wf['id'], u['id'], context={'source': 'new_member_scan'})
                n += 1
            except Exception:
                continue
    return n


def auto_enroll_new_visitors(since_hours: int = 72) -> int:
    """Pending / unapproved registrations → visitor workflows."""
    workflows = _active_workflows('new_visitor')
    if not workflows:
        return 0
    cur = _cur()
    cur.execute(
        """
        SELECT id FROM users
        WHERE (COALESCE(needs_approval,0)=1 OR role = 'pending')
          AND COALESCE(is_shadow_banned,0)=0
          AND created_at >= (UTC_TIMESTAMP() - INTERVAL %s HOUR)
        """,
        (since_hours,),
    )
    users = cur.fetchall() or []
    n = 0
    for wf in workflows:
        for u in users:
            try:
                if _already_enrolled(wf['id'], u['id']):
                    continue
                enroll_user(wf['id'], u['id'], context={'source': 'new_visitor_scan'})
                n += 1
            except Exception:
                continue
    return n


def auto_enroll_prayer_requests(since_hours: int = 48) -> int:
    """People who recently submitted a prayer request."""
    workflows = _active_workflows('prayer_request')
    if not workflows:
        return 0
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT p.id AS prayer_id, p.user_id, p.title, p.contributor_name
            FROM prayers p
            WHERE p.user_id IS NOT NULL
              AND p.date_posted >= (UTC_TIMESTAMP() - INTERVAL %s HOUR)
            ORDER BY p.date_posted DESC
            LIMIT 200
            """,
            (since_hours,),
        )
    except Exception:
        return 0
    rows = cur.fetchall() or []
    n = 0
    for wf in workflows:
        for row in rows:
            uid = row.get('user_id')
            if not uid:
                continue
            try:
                if _already_enrolled(wf['id'], uid):
                    continue
                enroll_user(
                    wf['id'],
                    uid,
                    context={
                        'source': 'prayer_scan',
                        'prayer_id': row.get('prayer_id'),
                        'prayer_title': row.get('title') or '',
                    },
                )
                n += 1
            except Exception:
                continue
    return n


def auto_enroll_volunteers(since_hours: int = 72) -> int:
    """Active volunteer team members not yet in onboarding workflows."""
    workflows = _active_workflows('volunteer_onboarding')
    if not workflows:
        return 0
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT m.user_id, m.team_id, t.name AS team_name
            FROM vol_team_members m
            LEFT JOIN vol_teams t ON t.id = m.team_id
            WHERE m.active = 1
            ORDER BY m.id DESC
            LIMIT 200
            """
        )
    except Exception:
        return 0
    rows = cur.fetchall() or []
    n = 0
    for wf in workflows:
        for row in rows:
            uid = row.get('user_id')
            if not uid:
                continue
            try:
                if _already_enrolled(wf['id'], uid):
                    continue
                enroll_user(
                    wf['id'],
                    uid,
                    context={
                        'source': 'volunteer_scan',
                        'team_id': row.get('team_id'),
                        'team_name': row.get('team_name') or 'Volunteer team',
                    },
                )
                n += 1
            except Exception:
                continue
    return n


def auto_enroll_giving_lapsed() -> int:
    """
    Members who have given before but not within N days (per workflow config).
    Default: 60 days inactive.
    """
    workflows = _active_workflows('giving_lapsed')
    if not workflows:
        return 0
    cur = _cur()
    n = 0
    for wf in workflows:
        cfg = parse_trigger_config(wf)
        days = int(cfg.get('days_inactive') or 60)
        if days < 7:
            days = 7
        try:
            cur.execute(
                """
                SELECT u.id AS user_id,
                       MAX(d.date) AS last_gift
                FROM users u
                JOIN donations d ON d.user_id = u.id
                WHERE COALESCE(u.needs_approval,0)=0
                  AND COALESCE(u.is_shadow_banned,0)=0
                  AND u.role NOT IN ('pending','banned')
                  AND COALESCE(u.accepts_emails,1)=1
                GROUP BY u.id
                HAVING last_gift IS NOT NULL
                   AND last_gift < (CURDATE() - INTERVAL %s DAY)
                LIMIT 300
                """,
                (days,),
            )
            rows = cur.fetchall() or []
        except Exception as e:
            print(f"giving_lapsed scan error: {e}")
            continue
        for row in rows:
            uid = row.get('user_id')
            if not uid:
                continue
            try:
                if _already_enrolled(wf['id'], uid):
                    continue
                enroll_user(
                    wf['id'],
                    uid,
                    context={
                        'source': 'giving_lapsed_scan',
                        'days_inactive': days,
                        'last_gift': str(row.get('last_gift') or ''),
                    },
                )
                n += 1
            except Exception:
                continue
    return n


def auto_enroll_follow_ups() -> int:
    """Open / in-progress pastoral care requests → follow-up drip for the member."""
    workflows = _active_workflows('follow_up')
    if not workflows:
        return 0
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT id, member_id, title, request_type, urgency, status
            FROM pastoral_care_requests
            WHERE status IN ('open', 'in_progress', 'assigned')
              AND member_id IS NOT NULL
            ORDER BY id DESC
            LIMIT 200
            """
        )
    except Exception:
        try:
            cur.execute(
                """
                SELECT id, member_id, title, request_type, urgency, status
                FROM pastoral_care_requests
                WHERE status IN ('open', 'in_progress')
                  AND member_id IS NOT NULL
                ORDER BY id DESC
                LIMIT 200
                """
            )
        except Exception as e:
            print(f"follow_up scan error: {e}")
            return 0
    rows = cur.fetchall() or []
    n = 0
    for wf in workflows:
        for row in rows:
            uid = row.get('member_id')
            if not uid:
                continue
            try:
                if _already_enrolled(wf['id'], uid):
                    continue
                enroll_user(
                    wf['id'],
                    uid,
                    context={
                        'source': 'follow_up_scan',
                        'care_id': row.get('id'),
                        'title': row.get('title') or row.get('request_type') or 'Care follow-up',
                        'urgency': row.get('urgency') or 'normal',
                        'care_type': row.get('request_type') or 'follow_up',
                    },
                )
                n += 1
            except Exception:
                continue
    return n


def run_all_auto_enrolls() -> dict:
    """Scanner suite used by the scheduler."""
    return {
        'new_visitor': auto_enroll_new_visitors(72),
        'new_member': auto_enroll_new_members(72),
        'prayer_request': auto_enroll_prayer_requests(48),
        'volunteer_onboarding': auto_enroll_volunteers(72),
        'giving_lapsed': auto_enroll_giving_lapsed(),
        'follow_up': auto_enroll_follow_ups(),
    }


def seed_default_workflows(created_by: int | None = None) -> dict:
    """
    Install starter automation templates if missing (by name).
    Safe to re-run — skips names that already exist.
    """
    templates = [
        {
            'name': 'New visitor welcome',
            'description': 'Auto for pending/new visitor registrations. Warm welcome + what to expect + invite to connect.',
            'trigger_type': 'new_visitor',
            'status': 'draft',
            'steps': [
                {
                    'delay_days': 0,
                    'channel': 'email',
                    'subject': 'Welcome to {{church_name}}, {{first_name}}!',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'We are so glad you found us. Your registration is being reviewed and we will be in touch soon.\n\n'
                        'In the meantime, feel free to explore upcoming events and prayer on our site.\n\n'
                        'Blessings,\n{{church_name}}'
                    ),
                },
                {
                    'delay_days': 2,
                    'channel': 'notify_pastoral',
                    'subject': 'New visitor to follow up: {{full_name}}',
                    'body': 'A new visitor registered. Please consider a personal welcome call or text.',
                },
            ],
        },
        {
            'name': 'New member welcome series',
            'description': 'Approved members: day 0 welcome, day 3 get involved, day 7 small groups.',
            'trigger_type': 'new_member',
            'status': 'draft',
            'steps': [
                {
                    'delay_days': 0,
                    'channel': 'email',
                    'subject': 'Welcome to the {{church_name}} family!',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Your account is active — welcome! We are grateful you are here.\n\n'
                        'Next steps: update your profile, check the events calendar, and say hello on Sunday.\n\n'
                        'With love,\n{{church_name}}'
                    ),
                },
                {
                    'delay_days': 3,
                    'channel': 'email',
                    'subject': 'Ways to get involved at {{church_name}}',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Looking for community? Browse volunteer teams, prayer, and upcoming events when you log in.\n\n'
                        'We would love to help you find your place.\n\n'
                        '— {{church_name}}'
                    ),
                },
                {
                    'delay_days': 7,
                    'channel': 'email',
                    'subject': 'One week in — how can we pray for you?',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'It has been a week since you joined. If you have a prayer need or question, reply to this email or submit a prayer request on the site.\n\n'
                        'Blessings,\n{{church_name}}'
                    ),
                },
            ],
        },
        {
            'name': 'Prayer request follow-up',
            'description': 'When someone submits a prayer: confirm receipt, notify pastoral team, check in later.',
            'trigger_type': 'prayer_request',
            'status': 'draft',
            'steps': [
                {
                    'delay_days': 0,
                    'channel': 'email',
                    'subject': 'We received your prayer request',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Thank you for trusting us with “{{prayer_title}}”. Our team is praying with you.\n\n'
                        'If this is urgent, please also call the church office.\n\n'
                        '— {{church_name}}'
                    ),
                },
                {
                    'delay_days': 0,
                    'channel': 'notify_pastoral',
                    'subject': 'New prayer request from {{full_name}}',
                    'body': 'Prayer submitted: {{prayer_title}}. Please review and pray with this person.',
                },
                {
                    'delay_days': 7,
                    'channel': 'email',
                    'subject': 'Checking in on your prayer',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'We wanted to check in about “{{prayer_title}}”. How are you doing? '
                        'Reply anytime — we are here.\n\n'
                        '— {{church_name}}'
                    ),
                },
            ],
        },
        {
            'name': 'Volunteer onboarding',
            'description': 'When someone joins a volunteer team: welcome, expectations, schedule tips.',
            'trigger_type': 'volunteer_onboarding',
            'status': 'draft',
            'steps': [
                {
                    'delay_days': 0,
                    'channel': 'email',
                    'subject': 'Welcome to the {{team_name}} team!',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Thank you for serving on {{team_name}} at {{church_name}}!\n\n'
                        'You will receive schedule reminders for your assignments. '
                        'If you have questions, reply to this message or contact your team lead.\n\n'
                        'Grateful for you,\n{{church_name}}'
                    ),
                },
                {
                    'delay_days': 3,
                    'channel': 'email',
                    'subject': 'Volunteer tips & next steps',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Quick tips: check the volunteer schedule regularly, arrive a few minutes early, '
                        'and let your lead know if you need a sub.\n\n'
                        'Thank you for serving!\n{{church_name}}'
                    ),
                },
            ],
        },
        {
            'name': 'Giving reminder (lapsed donors)',
            'description': 'Gentle reminder for members who have given before but not in 60+ days. Never guilt-based.',
            'trigger_type': 'giving_lapsed',
            'trigger_config': {'days_inactive': 60},
            'status': 'draft',
            'steps': [
                {
                    'delay_days': 0,
                    'channel': 'email',
                    'subject': 'A note of gratitude from {{church_name}}',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'We are thankful for your partnership in the gospel. This is a gentle reminder that '
                        'online and in-person giving remains available if you would like to continue supporting the ministry.\n\n'
                        'There is no pressure — only gratitude. If finances are tight right now, please know we are praying for you.\n\n'
                        'With appreciation,\n{{church_name}}'
                    ),
                },
            ],
        },
        {
            'name': 'Pastoral care follow-up series',
            'description': 'When a care request is open: check-in emails + optional care task for the team.',
            'trigger_type': 'follow_up',
            'status': 'draft',
            'steps': [
                {
                    'delay_days': 0,
                    'channel': 'email',
                    'subject': 'We are walking with you',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Our pastoral team is aware of your need and is praying for you regarding “{{title}}”. '
                        'You are not alone.\n\n'
                        'If something has changed or you need to talk sooner, reply to this email.\n\n'
                        'Care and peace,\n{{church_name}}'
                    ),
                },
                {
                    'delay_days': 3,
                    'channel': 'notify_pastoral',
                    'subject': 'Care follow-up due: {{full_name}}',
                    'body': 'Open care item “{{title}}” — please update notes or schedule a visit.',
                },
                {
                    'delay_days': 7,
                    'channel': 'email',
                    'subject': 'Checking in from {{church_name}}',
                    'body': (
                        'Hi {{first_name}},\n\n'
                        'Just checking in a week later. How are you doing? We continue to pray for you.\n\n'
                        '— {{church_name}} pastoral team'
                    ),
                },
            ],
        },
    ]

    created = 0
    skipped = 0
    cur = _cur()
    for tmpl in templates:
        cur.execute("SELECT id FROM comm_workflows WHERE name = %s LIMIT 1", (tmpl['name'],))
        if cur.fetchone():
            skipped += 1
            continue
        wid = create_workflow(
            {
                'name': tmpl['name'],
                'description': tmpl['description'],
                'trigger_type': tmpl['trigger_type'],
                'trigger_config': tmpl.get('trigger_config'),
                'status': tmpl.get('status') or 'draft',
            },
            created_by,
        )
        for i, step in enumerate(tmpl['steps']):
            save_step(wid, {**step, 'step_order': i})
        created += 1
    return {'created': created, 'skipped': skipped}


def recent_log(limit=40) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT * FROM comm_message_log
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall() or [])


def dashboard_stats() -> dict:
    cur = _cur()
    stats = {}
    for key, sql in [
        ('campaigns', "SELECT COUNT(*) AS n FROM comm_campaigns"),
        ('campaigns_sent', "SELECT COUNT(*) AS n FROM comm_campaigns WHERE status='sent'"),
        ('workflows_active', "SELECT COUNT(*) AS n FROM comm_workflows WHERE status='active'"),
        ('enrollments_active', "SELECT COUNT(*) AS n FROM comm_workflow_enrollments WHERE status='active'"),
        ('messages_7d', "SELECT COUNT(*) AS n FROM comm_message_log WHERE created_at >= (UTC_TIMESTAMP() - INTERVAL 7 DAY)"),
    ]:
        try:
            cur.execute(sql)
            stats[key] = int((cur.fetchone() or {}).get('n') or 0)
        except Exception:
            stats[key] = 0
    stats['sms'] = get_sms_settings()
    return stats


def list_enrollments(workflow_id: int, limit=100) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT e.*, u.first_name, u.last_name, u.email
        FROM comm_workflow_enrollments e
        JOIN users u ON u.id = e.user_id
        WHERE e.workflow_id = %s
        ORDER BY e.enrolled_at DESC
        LIMIT %s
        """,
        (workflow_id, limit),
    )
    return list(cur.fetchall() or [])
