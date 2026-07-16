# Aggregate-only datasets for AI Insights (no raw PII / donor lists by default).

from __future__ import annotations

import json
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


def security_aggregate() -> dict:
    try:
        from app.routes.security.queries import summary_stats

        stats = summary_stats() or {}
        # Prefer coarse numbers; drop any IP-looking keys if present
        safe = {}
        for k, v in stats.items():
            lk = str(k).lower()
            if any(x in lk for x in ('ip', 'email', 'user', 'password', 'token')):
                continue
            if isinstance(v, (int, float, str, bool)) or v is None:
                safe[k] = v
            elif isinstance(v, (list, dict)):
                safe[k] = _serialize(v)[:20] if isinstance(v, list) else _serialize(v)
        safe['note'] = 'Coarse security stats only; IPs and identities omitted.'
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


def dataset_for(report_type: str) -> dict:
    report_type = (report_type or '').strip().lower()
    if report_type == 'donations':
        return donations_aggregate()
    if report_type == 'attendance':
        return attendance_aggregate()
    if report_type == 'security':
        return security_aggregate()
    if report_type == 'tickets':
        return tickets_aggregate()
    if report_type == 'overview':
        return overview_aggregate()
    return {'error': f'Unknown report type: {report_type}'}


def prompt_for(report_type: str, dataset: dict, extra_question: str = '') -> tuple[str, str]:
    system = (
        'You are an assistant for church administrators. '
        'Use only the provided JSON aggregates. Do not invent names, emails, or exact people. '
        'Be practical, concise, and pastoral in tone. Use short bullet sections. '
        'If data is sparse or missing, say so clearly instead of guessing. '
        'Keep the whole answer under ~400 words.'
    )
    titles = {
        'donations': 'Giving / donations report',
        'attendance': 'Attendance trends report',
        'security': 'Security operations brief',
        'tickets': 'Support tickets workload brief',
        'overview': 'Church operations overview',
    }
    title = titles.get(report_type, 'Church report')
    # Compact JSON (no indent) — smaller payload, faster for overloaded providers
    payload = json.dumps(dataset, default=str, separators=(',', ':'))[:10000]
    user = (
        f'Write a clear {title} for leadership from this aggregate JSON only:\n'
        f'{payload}\n\n'
        'Sections: 1) Snapshot 2) Trends 3) Risks/gaps 4) 3–5 next actions. '
        'If counts are very low, note that the sample is small and avoid overclaiming trends.'
    )
    q = (extra_question or '').strip()
    if q:
        user += f'\n\nAdditional focus from the administrator: {q[:500]}'
    return system, user
