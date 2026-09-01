# Aggregate-only datasets for AI Insights (no raw PII / donor lists by default).

from __future__ import annotations

import json
import re
from datetime import timedelta

import pymysql

from app.models.db import get_db
from app.utils.time_utils import now_church


def _year_month():
    n = now_church()
    return n.year, n.month


def donations_aggregate(year: int | None = None) -> dict:
    y, _ = _year_month()
    year = year or y
    # Prefer enterprise aggregates when email-import tables exist
    try:
        from app.donations_import.service import enterprise_report
        er = enterprise_report(year)
        return {
            'year': year,
            'gift_count': er.get('gift_count'),
            'total_amount': er.get('total_amount'),
            'by_channel': _serialize(er.get('by_channel') or []),
            'by_source': _serialize(er.get('by_source') or []),
            'receipt_pipeline': _serialize(er.get('receipt_pipeline') or []),
            'email_import_queue': _serialize(er.get('email_import_queue') or []),
            'recurring': _serialize(er.get('recurring') or []),
            'note': 'Enterprise aggregates only — individual donor names omitted for privacy.',
        }
    except Exception:
        pass
    try:
        from app.models.donation import get_reports_data

        data = get_reports_data(selected_year=year, selected_month=None, donor_type_filter=None)
        # Strip personal donor identity from AI payload
        safe = {
            'year': year,
            'total_amount': float(data.get('total') or data.get('year_total') or 0)
            if not isinstance(data.get('total'), (dict, list))
            else data.get('total'),
            'counts': {},
            'by_method': [],
            'by_month': [],
            'by_donor_type': [],
            'note': 'Aggregates only — individual donor names omitted for privacy.',
        }
        # Best-effort map of known report keys
        for key in ('monthly_totals', 'by_month', 'months', 'method_totals', 'type_totals', 'totals'):
            if key in data and data[key] is not None:
                val = data[key]
                if key in ('method_totals',) or 'method' in key:
                    safe['by_method'] = _serialize(val)
                elif 'month' in key:
                    safe['by_month'] = _serialize(val)
                elif 'type' in key:
                    safe['by_donor_type'] = _serialize(val)
                else:
                    safe['counts'][key] = _serialize(val)
        # Prefer explicit fields if present
        if data.get('grand_total') is not None:
            safe['total_amount'] = _num(data.get('grand_total'))
        if data.get('total_donations') is not None:
            safe['donation_count'] = int(data.get('total_donations') or 0)
        if data.get('reports'):
            safe['reports'] = _serialize(data.get('reports'))
        # Never include top_donors with names
        if data.get('top_donors'):
            safe['top_donor_amounts_only'] = [
                {'rank': i + 1, 'amount': _num(row.get('total') or row.get('amount'))}
                for i, row in enumerate(list(data.get('top_donors') or [])[:10])
                if isinstance(row, dict)
            ]
        return safe
    except Exception as e:
        return _sql_donations_fallback(year, str(e))


def _sql_donations_fallback(year: int, err: str) -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
            FROM donations
            WHERE YEAR(STR_TO_DATE(date, '%%Y-%%m-%%d')) = %s
               OR YEAR(date) = %s
            """,
            (year, year),
        )
        row = cur.fetchone() or {}
        return {
            'year': year,
            'donation_count': int(row.get('cnt') or 0),
            'total_amount': _num(row.get('total')),
            'note': 'Aggregate fallback. ' + (err[:120] if err else ''),
        }
    except Exception:
        try:
            cur.execute('SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM donations')
            row = cur.fetchone() or {}
            return {
                'year': year,
                'donation_count': int(row.get('cnt') or 0),
                'total_amount': _num(row.get('total')),
                'note': 'All-time totals (year filter unavailable).',
            }
        except Exception as e2:
            return {'error': 'Could not load donation aggregates', 'detail': str(e2)[:120]}


def attendance_aggregate(days: int = 90) -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    days = max(14, min(int(days or 90), 365))
    try:
        cur.execute(
            """
            SELECT DATE(service_date) AS d, COUNT(*) AS headcount
            FROM attendance
            WHERE service_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY DATE(service_date)
            ORDER BY d DESC
            LIMIT 120
            """,
            (days,),
        )
        rows = cur.fetchall() or []
        series = [
            {'date': str(r.get('d')), 'headcount': int(r.get('headcount') or 0)} for r in rows
        ]
        counts = [s['headcount'] for s in series]
        avg = round(sum(counts) / len(counts), 1) if counts else 0
        return {
            'window_days': days,
            'days_with_checkins': len(series),
            'average_headcount': avg,
            'peak_headcount': max(counts) if counts else 0,
            'recent_days': series[:30],
            'note': 'Headcounts only — no member names.',
        }
    except Exception as e:
        return {'error': 'Could not load attendance aggregates', 'detail': str(e)[:120]}


def mask_ip_for_ai(ip: str | None, *, detail: str = 'prefix') -> str:
    """
    Privacy-safe IP for AI payloads.

    detail:
      - 'prefix' (default): IPv4 → 99.199.89.x  |  IPv6 → first 3 hextets + :x:x:x:x
      - 'full': exact address (only when operator explicitly opts in)
    """
    raw = (ip or '').strip()
    if not raw:
        return ''
    mode = (detail or 'prefix').strip().lower()
    if mode in ('full', 'exact', 'reveal', 'unmasked'):
        return raw[:80]

    # IPv4 dotted-quad
    if '.' in raw and ':' not in raw:
        parts = raw.split('.')
        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return f'{parts[0]}.{parts[1]}.{parts[2]}.x'
        # partial/malformed — still redact last segment if possible
        if len(parts) >= 3:
            return f'{parts[0]}.{parts[1]}.{parts[2]}.x'
        return 'x.x.x.x'

    # IPv6 (including compressed forms)
    if ':' in raw:
        # Strip zone id (fe80::1%eth0)
        core = raw.split('%', 1)[0]
        # Expand :: once for consistent hextet count
        if '::' in core:
            left, _, right = core.partition('::')
            left_parts = [p for p in left.split(':') if p != '']
            right_parts = [p for p in right.split(':') if p != '']
            missing = 8 - (len(left_parts) + len(right_parts))
            if missing < 0:
                missing = 0
            hextets = left_parts + (['0'] * missing) + right_parts
        else:
            hextets = [p for p in core.split(':') if p != '']
        # Keep first 3 hextets (network-ish), mask the rest
        keep = []
        for h in hextets[:3]:
            # normalize to lowercase hex-ish token
            keep.append(h.lower()[:4] if h else '0')
        while len(keep) < 3:
            keep.append('0')
        return ':'.join(keep) + ':x:x:x:x'

    return 'x'


def _safe_notes_for_ai(notes: str | None, *, max_len: int = 120) -> str:
    """Drop obvious identity tokens from free-text security notes."""
    if not notes:
        return ''
    text = str(notes)
    # emails
    text = re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[email]', text)
    # long tokens / keys
    text = re.sub(r'\b[A-Fa-f0-9]{24,}\b', '[token]', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]


def security_aggregate(*, ip_detail: str = 'prefix') -> dict:
    """
    Security brief for AI: counts + sample events/bans with IPs masked by default.

    ip_detail: 'prefix' (99.199.89.x) or 'full' (exact IP — opt-in only).
    """
    try:
        from app.routes.security.queries import (
            summary_stats,
            list_security_events,
            list_attack_stats,
            list_reputation_rows,
            list_event_types,
        )

        detail = (ip_detail or 'prefix').strip().lower()
        if detail not in ('prefix', 'full'):
            detail = 'prefix'

        stats = summary_stats() or {}
        safe: dict = {
            'events_24h': int(stats.get('events_24h') or 0),
            'events_total': int(stats.get('events_total') or 0),
            'active_temp_bans': int(stats.get('active_temp_bans') or 0),
            'perm_bans': int(stats.get('perm_bans') or 0),
            'low_reputation': int(stats.get('low_reputation') or 0),
            'account_login_locks': int(stats.get('account_login_locks') or 0),
            'attack_types_tracked': int(stats.get('attack_types') or 0),
            'ip_detail_level': detail,
        }

        # Event-type mix (no IPs)
        try:
            types = list_event_types() or []
            safe['event_types_seen'] = types[:40]
        except Exception:
            safe['event_types_seen'] = []

        # Recent events — IP masked unless full
        try:
            events, _total = list_security_events(limit=35)
            recent = []
            for ev in events or []:
                recent.append({
                    'when': str(ev.get('timestamp') or '')[:19],
                    'event_type': ev.get('event_type') or '',
                    'ip': mask_ip_for_ai(ev.get('ip'), detail=detail),
                    'reputation_score': ev.get('reputation_score'),
                    'behavior_grade': ev.get('behavior_grade') or '',
                    'notes': _safe_notes_for_ai(ev.get('notes')),
                })
            safe['recent_events'] = recent
            # Prefix frequency — useful even when full IPs are redacted
            prefix_counts: dict[str, int] = {}
            for row in recent:
                p = row.get('ip') or ''
                if p:
                    prefix_counts[p] = prefix_counts.get(p, 0) + 1
            top_prefixes = sorted(
                ({'ip_or_prefix': k, 'events_in_sample': v} for k, v in prefix_counts.items()),
                key=lambda x: -x['events_in_sample'],
            )[:15]
            safe['top_ip_prefixes_in_sample'] = top_prefixes
        except Exception as exc:
            safe['recent_events'] = []
            safe['events_error'] = str(exc)[:100]

        # Attack stats
        try:
            attacks = list_attack_stats() or []
            safe['attack_stats'] = [
                {
                    'attack_type': a.get('attack_type') or '',
                    'total_attempts': a.get('total_attempts'),
                    'blocked_count': a.get('blocked_count'),
                    'last_attack_ip': mask_ip_for_ai(a.get('last_attack_ip'), detail=detail),
                    'last_attack_time': str(a.get('last_attack_time') or '')[:19],
                    'severity_level': a.get('severity_level'),
                    'notes': _safe_notes_for_ai(a.get('notes'), max_len=80),
                }
                for a in attacks[:25]
            ]
        except Exception:
            safe['attack_stats'] = []

        # Active bans / low reputation — no usernames
        try:
            bans = list_reputation_rows(filter_mode='bans', limit=30) or []
            safe['active_bans_sample'] = [
                {
                    'ip': mask_ip_for_ai(b.get('ip'), detail=detail),
                    'score': b.get('score'),
                    'grade': b.get('grade') or '',
                    'ban_until': str(b.get('ban_until') or '')[:19] or None,
                    'ban_count': b.get('ban_count'),
                    'ban_reason': _safe_notes_for_ai(b.get('ban_reason'), max_len=100),
                    'last_seen': str(b.get('last_seen') or '')[:19],
                }
                for b in bans
            ]
        except Exception:
            safe['active_bans_sample'] = []

        try:
            low = list_reputation_rows(filter_mode='low', limit=20) or []
            safe['low_reputation_sample'] = [
                {
                    'ip': mask_ip_for_ai(b.get('ip'), detail=detail),
                    'score': b.get('score'),
                    'grade': b.get('grade') or '',
                    'negative_points': b.get('negative_points'),
                    'last_seen': str(b.get('last_seen') or '')[:19],
                }
                for b in low
            ]
        except Exception:
            safe['low_reputation_sample'] = []

        if detail == 'full':
            safe['note'] = (
                'Security brief with FULL IP addresses included by operator choice. '
                'Treat as sensitive. No account emails/usernames.'
            )
        else:
            safe['note'] = (
                'Security brief: IPs shown as network prefix only '
                '(IPv4 like 99.199.89.x; IPv6 first 3 hextets + :x:x:x:x). '
                'Last octet / host portion redacted. No account emails/usernames.'
            )
        return safe
    except Exception as e:
        return {'error': 'Security stats unavailable', 'detail': str(e)[:120]}


def tickets_aggregate() -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM tickets
            GROUP BY status
            """
        )
        by_status = {r['status']: int(r['cnt']) for r in (cur.fetchall() or [])}
        cur.execute(
            """
            SELECT priority, COUNT(*) AS cnt
            FROM tickets
            WHERE status IN ('open', 'in_progress')
            GROUP BY priority
            """
        )
        open_by_priority = {r['priority']: int(r['cnt']) for r in (cur.fetchall() or [])}
        return {
            'by_status': by_status,
            'open_by_priority': open_by_priority,
            'note': 'Ticket metadata only — no titles or comments sent to AI.',
        }
    except Exception as e:
        return {'error': 'Tickets aggregates unavailable', 'detail': str(e)[:120]}


def overview_aggregate() -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    out = {'generated_at': now_church().isoformat()}
    for label, sql in (
        ('members', "SELECT COUNT(*) AS c FROM users WHERE COALESCE(needs_approval,0)=0"),
        ('pending_members', "SELECT COUNT(*) AS c FROM users WHERE COALESCE(needs_approval,0)=1"),
        ('events_upcoming', "SELECT COUNT(*) AS c FROM events WHERE event_date >= CURDATE()"),
        ('open_tickets', "SELECT COUNT(*) AS c FROM tickets WHERE status IN ('open','in_progress')"),
    ):
        try:
            cur.execute(sql)
            out[label] = int((cur.fetchone() or {}).get('c') or 0)
        except Exception:
            out[label] = None
    out['donations'] = donations_aggregate()
    out['attendance'] = attendance_aggregate(60)
    out['tickets'] = tickets_aggregate()
    out['note'] = 'High-level church operations snapshot (aggregates only).'
    return out


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _serialize(val, depth=0):
    if depth > 4:
        return str(val)[:80]
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, list):
        return [_serialize(x, depth + 1) for x in val[:40]]
    if isinstance(val, dict):
        out = {}
        for i, (k, v) in enumerate(val.items()):
            if i > 40:
                break
            sk = str(k)
            if any(x in sk.lower() for x in ('email', 'phone', 'password', 'token', 'ip_address', 'name')):
                # keep structural keys like donor_type
                if sk.lower() in ('name', 'email', 'phone', 'donor_email', 'donor_phone', 'username'):
                    continue
            out[sk] = _serialize(v, depth + 1)
        return out
    if hasattr(val, 'isoformat'):
        try:
            return val.isoformat()
        except Exception:
            return str(val)
    return str(val)[:120]


def dataset_for(report_type: str, *, ip_detail: str = 'prefix') -> dict:
    report_type = (report_type or '').strip().lower()
    if report_type == 'donations':
        return donations_aggregate()
    if report_type == 'attendance':
        return attendance_aggregate()
    if report_type == 'security':
        return security_aggregate(ip_detail=ip_detail)
    if report_type == 'tickets':
        return tickets_aggregate()
    if report_type == 'overview':
        return overview_aggregate()
    return {'error': f'Unknown report type: {report_type}'}


def prompt_for(report_type: str, dataset: dict, extra_question: str = '') -> tuple[str, str]:
    from app.utils.ai_format import PASTOR_VOICE_SYSTEM

    system = (
        PASTOR_VOICE_SYSTEM
        + ' Use only the provided JSON aggregates. '
        'Do not invent names, emails, or exact people. '
        'Keep the whole answer under about 350 words.'
    )
    if report_type == 'security':
        level = (dataset or {}).get('ip_detail_level') or 'prefix'
        if level == 'full':
            system += (
                ' IP addresses in this payload may be complete. '
                'Discuss them carefully; do not invent addresses.'
            )
        else:
            system += (
                ' IP addresses are network-prefix only '
                '(IPv4 like 99.199.89.x; IPv6 first three hextets + masked host). '
                'Treat matching prefixes as the same network cluster when useful. '
                'Do not invent full host addresses.'
            )
    titles = {
        'donations': 'giving numbers',
        'attendance': 'attendance numbers',
        'security': 'security stats',
        'tickets': 'support ticket workload',
        'overview': 'church operations snapshot',
    }
    title = titles.get(report_type, 'church data')
    # Security payloads are larger (event samples); allow more room
    cap = 18000 if report_type == 'security' else 10000
    payload = json.dumps(dataset, default=str, separators=(',', ':'))[:cap]
    user = (
        f'Talk through this {title} with me like we are in a staff meeting. '
        f'Here is the aggregate JSON (only source of truth):\n{payload}\n\n'
        'Cover, in plain prose (no markdown headings):\n'
        '- What stands out right now\n'
        '- Any trend or pattern worth noticing\n'
        '- Risks or gaps, if any\n'
        '- A few concrete next steps I could take this month\n'
        'If the numbers are sparse, say the sample is small and do not overclaim.'
    )
    if report_type == 'security':
        user += (
            '\nFor security: call out noisy event types, repeat prefixes/networks, '
            'ban load, and practical hardening steps. '
            'When IPs are prefix-masked, reason at the network level.'
        )
    q = (extra_question or '').strip()
    if q:
        user += f'\n\nMy extra question: {q[:500]}'
    return system, user
