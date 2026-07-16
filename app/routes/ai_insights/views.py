# AI Insights — secure aggregate reports for leadership.
# Cloud AI is optional; Gemini/OpenAI/Grok keys are configured under Settings → AI.

from flask import (
    flash, jsonify, redirect, render_template, request, session, url_for,
)

from app.models.log import log_change
from app.utils.ai_client import ai_status, run_insight
from app.utils.decorators import login_required, permission_required
from app.utils.helpers import contains_censored_word
from app.utils.permissions import user_has_permission

from . import ai_insights_bp
from .data import dataset_for, prompt_for

REPORTS = [
    {
        'id': 'overview',
        'title': 'Operations overview',
        'icon': 'fa-chart-pie',
        'desc': 'Members, events, tickets, giving and attendance at a glance.',
        'permission': None,  # any insights user
    },
    {
        'id': 'donations',
        'title': 'Giving summary',
        'icon': 'fa-hand-holding-dollar',
        'desc': 'Aggregate donation totals and trends (no donor names sent to AI).',
        'permission': 'view_donations',
    },
    {
        'id': 'attendance',
        'title': 'Attendance trends',
        'icon': 'fa-clipboard-user',
        'desc': 'Headcounts and patterns — no individual check-in names.',
        'permission': 'manage_attendance',
    },
    {
        'id': 'security',
        'title': 'Security brief',
        'icon': 'fa-shield-halved',
        'desc': 'High-level attack and ban stats (IPs redacted).',
        'permission': 'manage_security',
    },
    {
        'id': 'tickets',
        'title': 'Support tickets',
        'icon': 'fa-ticket',
        'desc': 'Open workload by status and priority (no ticket text).',
        'permission': 'manage_tickets',
    },
]


def can_use_ai_insights() -> bool:
    role = session.get('user_role')
    if role in ('Owner', 'Admin', 'Staff'):
        return True
    return user_has_permission('use_ai_insights')


def _can_run_report(report_id: str) -> bool:
    if not can_use_ai_insights():
        return False
    rep = next((r for r in REPORTS if r['id'] == report_id), None)
    if not rep:
        return False
    perm = rep.get('permission')
    if not perm:
        return True
    if session.get('user_role') in ('Owner', 'Admin', 'Staff'):
        return True
    return user_has_permission(perm)


@ai_insights_bp.route('/')
@login_required
def index():
    if not can_use_ai_insights():
        flash('You do not have permission to use AI Insights.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    status = ai_status()
    available = []
    for r in REPORTS:
        item = dict(r)
        item['allowed'] = _can_run_report(r['id'])
        available.append(item)

    return render_template(
        'ai_insights/index.html',
        status=status,
        reports=available,
        can_configure=session.get('user_role') in ('Owner', 'Admin')
        or user_has_permission('manage_settings'),
    )


@ai_insights_bp.route('/report/<report_type>', methods=['GET', 'POST'])
@login_required
def report(report_type):
    report_type = (report_type or '').strip().lower()
    if report_type not in {r['id'] for r in REPORTS}:
        flash('Unknown report.', 'error')
        return redirect(url_for('ai_insights.index'))
    if not _can_run_report(report_type):
        flash('You do not have permission for this report.', 'error')
        return redirect(url_for('ai_insights.index'))

    meta = next(r for r in REPORTS if r['id'] == report_type)
    status = ai_status()
    dataset = dataset_for(report_type)
    insight = None
    error = None
    extra = ''

    if request.method == 'POST':
        extra = (request.form.get('extra_question') or '').strip()
        if extra and contains_censored_word(extra):
            error = 'Your question contains prohibited content.'
        elif not status.get('configured'):
            error = 'Configure and enable an AI provider under Settings → AI Providers (Gemini, Grok, OpenAI, or Ollama).'
        else:
            system, user_prompt = prompt_for(report_type, dataset, extra)
            text, err, run_meta = run_insight(
                f'insights_{report_type}',
                system,
                user_prompt,
            )
            if err:
                error = err
            else:
                insight = text
                log_change(
                    session['user_id'],
                    'ai',
                    None,
                    report_type,
                    f"AI Insights: {report_type} via {run_meta.get('provider') or '?'}",
                )

    return render_template(
        'ai_insights/report.html',
        meta=meta,
        status=status,
        dataset=dataset,
        insight=insight,
        error=error,
        extra_question=extra,
    )


@ai_insights_bp.route('/api/generate', methods=['POST'])
@login_required
def api_generate():
    """JSON API for future UI polish — same security rules as form POST."""
    if not can_use_ai_insights():
        return jsonify({'ok': False, 'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    report_type = (data.get('report_type') or request.form.get('report_type') or '').strip().lower()
    extra = (data.get('extra_question') or request.form.get('extra_question') or '').strip()

    if report_type not in {r['id'] for r in REPORTS}:
        return jsonify({'ok': False, 'error': 'Unknown report type'}), 400
    if not _can_run_report(report_type):
        return jsonify({'ok': False, 'error': 'Permission denied for this report'}), 403
    if extra and contains_censored_word(extra):
        return jsonify({'ok': False, 'error': 'Prohibited content in question'}), 400

    status = ai_status()
    if not status.get('configured'):
        return jsonify({
            'ok': False,
            'error': 'AI not configured. Add a provider key under Settings → AI Providers.',
            'status': status,
        }), 400

    dataset = dataset_for(report_type)
    if dataset.get('error') and len(dataset) <= 2:
        return jsonify({'ok': False, 'error': dataset.get('error'), 'dataset': dataset}), 500

    system, user_prompt = prompt_for(report_type, dataset, extra)
    text, err, run_meta = run_insight(f'insights_{report_type}', system, user_prompt)
    if err:
        return jsonify({'ok': False, 'error': err, 'meta': run_meta}), 502

    log_change(
        session['user_id'],
        'ai',
        None,
        report_type,
        f"AI Insights API: {report_type}",
    )
    return jsonify({
        'ok': True,
        'insight': text,
        'meta': run_meta,
        'dataset_preview': {
            'keys': list(dataset.keys())[:20],
            'note': dataset.get('note'),
        },
    })


@ai_insights_bp.route('/api/status')
@login_required
def api_status():
    if not can_use_ai_insights():
        return jsonify({'ok': False, 'error': 'Permission denied'}), 403
    return jsonify({'ok': True, 'status': ai_status()})
