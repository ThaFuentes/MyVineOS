# Communications hub routes.

from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from app.models import communications as comm
from app.models.log import log_change
from app.utils.decorators import login_required, permission_required
from app.utils.time_utils import format_church

from . import communications_bp


def _uid():
    return session.get('user_id')


@communications_bp.route('/')
@login_required
@permission_required('send_emails')
def dashboard():
    stats = comm.dashboard_stats()
    campaigns = comm.list_campaigns(12)
    workflows = comm.list_workflows()
    log = comm.recent_log(15)
    log_change(_uid(), 'view', change_details='Opened Communications hub')
    return render_template(
        'communications/dashboard.html',
        stats=stats,
        campaigns=campaigns,
        workflows=workflows,
        message_log=log,
    )


# ── Campaigns (mass email / SMS) ────────────────────────────────────────────

@communications_bp.route('/campaigns')
@login_required
@permission_required('send_emails')
def campaigns_list():
    return render_template(
        'communications/campaigns.html',
        campaigns=comm.list_campaigns(80),
    )


@communications_bp.route('/campaigns/new', methods=['GET', 'POST'])
@login_required
@permission_required('send_emails')
def campaign_new():
    if request.method == 'POST':
        return _save_campaign_form()
    return render_template(
        'communications/campaign_form.html',
        campaign=None,
        groups=comm.list_groups_simple(),
        members=comm.list_members_for_picker(),
        audience_types=comm.AUDIENCE_TYPES,
        preview_count=None,
    )


@communications_bp.route('/campaigns/<int:campaign_id>', methods=['GET', 'POST'])
@login_required
@permission_required('send_emails')
def campaign_detail(campaign_id):
    campaign = comm.get_campaign(campaign_id)
    if not campaign:
        flash('Campaign not found.', 'error')
        return redirect(url_for('communications.campaigns_list'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        if action == 'save' and campaign['status'] == 'draft':
            return _save_campaign_form(campaign_id)
        if action == 'send_now':
            try:
                result = comm.prepare_and_send_campaign(campaign_id, force=True)
                flash(
                    f"Sent {result.get('sent', 0)} of {result.get('total', 0)} "
                    f"({result.get('failed', 0)} failed).",
                    'success' if result.get('sent') else 'error',
                )
                log_change(_uid(), 'create', campaign_id, change_details=f"Sent campaign: {campaign.get('title')}")
            except Exception as e:
                flash(str(e), 'error')
            return redirect(url_for('communications.campaign_detail', campaign_id=campaign_id))
        if action == 'schedule':
            when = request.form.get('scheduled_at')
            if not when:
                flash('Pick a schedule date/time.', 'error')
            else:
                # Store as church-local naive; compare with utc in processor may be off slightly — ok for v1
                comm.update_campaign(campaign_id, {'status': 'scheduled', 'scheduled_at': when.replace('T', ' ')})
                flash('Campaign scheduled. It will send when the scheduler runs after that time.', 'success')
            return redirect(url_for('communications.campaign_detail', campaign_id=campaign_id))
        if action == 'cancel':
            if campaign['status'] in ('draft', 'scheduled'):
                comm.update_campaign(campaign_id, {'status': 'cancelled'})
                flash('Campaign cancelled.', 'info')
            return redirect(url_for('communications.campaigns_list'))
        if action == 'preview_count':
            ids = request.form.getlist('audience_ids')
            n = comm.preview_audience_count(
                request.form.get('channel') or campaign['channel'],
                request.form.get('audience_type') or campaign['audience_type'],
                audience_ref=request.form.get('audience_ref') or campaign.get('audience_ref'),
                audience_ids=ids or campaign.get('audience_ids'),
            )
            flash(f'About {n} recipients match this audience right now.', 'info')
            return redirect(url_for('communications.campaign_detail', campaign_id=campaign_id))

    recipients = []
    if campaign['status'] in ('sent', 'sending'):
        from app.models.db import get_db
        import pymysql
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            """
            SELECT * FROM comm_campaign_recipients
            WHERE campaign_id=%s ORDER BY id DESC LIMIT 200
            """,
            (campaign_id,),
        )
        recipients = list(cur.fetchall() or [])

    return render_template(
        'communications/campaign_detail.html',
        campaign=campaign,
        recipients=recipients,
        groups=comm.list_groups_simple(),
        members=comm.list_members_for_picker(),
        audience_types=comm.AUDIENCE_TYPES,
        sms=comm.get_sms_settings(),
    )


def _save_campaign_form(campaign_id=None):
    channel = (request.form.get('channel') or 'email').lower()
    if channel == 'sms' and len((request.form.get('body') or '')) > 1600:
        flash('SMS body is too long (max ~1600 characters).', 'error')
        return redirect(request.referrer or url_for('communications.campaign_new'))

    data = {
        'channel': channel,
        'title': request.form.get('title'),
        'subject': request.form.get('subject'),
        'body': request.form.get('body'),
        'audience_type': request.form.get('audience_type') or 'all_opt_in',
        'audience_ref': request.form.get('audience_ref') or None,
        'audience_ids': request.form.getlist('audience_ids'),
        'notes': request.form.get('notes'),
        'status': 'draft',
    }
    if not (data['body'] or '').strip():
        flash('Message body is required.', 'error')
        return redirect(request.referrer or url_for('communications.campaign_new'))
    if channel == 'email' and not (data['subject'] or '').strip():
        flash('Email subject is required.', 'error')
        return redirect(request.referrer or url_for('communications.campaign_new'))

    try:
        if campaign_id:
            comm.update_campaign(campaign_id, data)
            flash('Campaign saved.', 'success')
            cid = campaign_id
        else:
            cid = comm.create_campaign(data, _uid())
            flash('Campaign created as draft.', 'success')
            log_change(_uid(), 'create', cid, change_details=f"Created {channel} campaign")
        return redirect(url_for('communications.campaign_detail', campaign_id=cid))
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('communications.campaign_new'))


# ── SMS settings ────────────────────────────────────────────────────────────

@communications_bp.route('/sms-settings', methods=['GET', 'POST'])
@login_required
@permission_required('send_emails')
def sms_settings():
    if request.method == 'POST':
        if request.form.get('action') == 'test':
            phone = request.form.get('test_phone')
            result = comm.send_sms(phone, request.form.get('test_body') or 'MyVineOS SMS test message.')
            if result.get('ok'):
                flash(
                    f"SMS {'test-logged' if result.get('test_mode') else 'sent'} to {result.get('to')}.",
                    'success',
                )
            else:
                flash(result.get('error') or 'SMS failed.', 'error')
            return redirect(url_for('communications.sms_settings'))

        comm.save_sms_settings({
            'enabled': request.form.get('enabled') == '1',
            'provider': request.form.get('provider') or 'twilio',
            'account_sid': request.form.get('account_sid'),
            'auth_token': request.form.get('auth_token'),
            'from_number': request.form.get('from_number'),
            'test_mode': request.form.get('test_mode') == '1',
            'from_name': request.form.get('from_name'),
        })
        flash('SMS settings saved.', 'success')
        log_change(_uid(), 'update', change_details='Updated SMS provider settings')
        return redirect(url_for('communications.sms_settings'))

    return render_template(
        'communications/sms_settings.html',
        sms=comm.get_sms_settings(),
    )


# ── Workflows / drips ───────────────────────────────────────────────────────

@communications_bp.route('/workflows')
@login_required
@permission_required('send_emails')
def workflows_list():
    return render_template(
        'communications/workflows.html',
        workflows=comm.list_workflows(),
        trigger_labels=comm.TRIGGER_LABELS,
    )


@communications_bp.route('/workflows/seed-defaults', methods=['POST'])
@login_required
@permission_required('send_emails')
def workflows_seed_defaults():
    result = comm.seed_default_workflows(_uid())
    flash(
        f"Installed {result.get('created', 0)} starter workflow(s) "
        f"({result.get('skipped', 0)} already present). Review, edit, then Activate each one.",
        'success',
    )
    log_change(_uid(), 'create', change_details='Seeded default automation workflows')
    return redirect(url_for('communications.workflows_list'))


@communications_bp.route('/workflows/new', methods=['GET', 'POST'])
@login_required
@permission_required('send_emails')
def workflow_new():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('Name your workflow.', 'error')
            return redirect(url_for('communications.workflow_new'))
        trigger = request.form.get('trigger_type') or 'manual'
        cfg = {}
        if trigger == 'giving_lapsed':
            try:
                cfg['days_inactive'] = max(7, int(request.form.get('days_inactive') or 60))
            except (TypeError, ValueError):
                cfg['days_inactive'] = 60
        wid = comm.create_workflow({
            'name': name,
            'description': request.form.get('description'),
            'trigger_type': trigger,
            'trigger_config': cfg or None,
            'status': 'draft',
        }, _uid())
        # Seed first welcome step
        comm.save_step(wid, {
            'delay_days': 0,
            'channel': 'email',
            'subject': 'Hello from {{church_name}}!',
            'body': (
                'Hi {{first_name}},\n\n'
                'This is the first step in an automated workflow.\n\n'
                'Blessings,\n{{church_name}}'
            ),
        })
        flash('Workflow created. Add steps, then Activate so triggers can enroll people.', 'success')
        return redirect(url_for('communications.workflow_detail', workflow_id=wid))
    return render_template(
        'communications/workflow_form.html',
        trigger_types=comm.TRIGGER_TYPES,
    )


@communications_bp.route('/workflows/<int:workflow_id>', methods=['GET', 'POST'])
@login_required
@permission_required('send_emails')
def workflow_detail(workflow_id):
    wf = comm.get_workflow(workflow_id)
    if not wf:
        flash('Workflow not found.', 'error')
        return redirect(url_for('communications.workflows_list'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        try:
            if action == 'save':
                trigger = request.form.get('trigger_type') or wf.get('trigger_type') or 'manual'
                cfg = comm.parse_trigger_config(wf)
                if trigger == 'giving_lapsed':
                    try:
                        cfg['days_inactive'] = max(7, int(request.form.get('days_inactive') or cfg.get('days_inactive') or 60))
                    except (TypeError, ValueError):
                        cfg['days_inactive'] = 60
                comm.update_workflow(workflow_id, {
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'trigger_type': trigger,
                    'trigger_config': cfg,
                })
                flash('Workflow saved.', 'success')
            elif action == 'activate':
                steps = comm.list_steps(workflow_id)
                if not steps:
                    flash('Add steps before activating.', 'error')
                else:
                    comm.update_workflow(workflow_id, {'status': 'active'})
                    flash('Workflow is active. Triggers and the scheduler will enroll people automatically.', 'success')
            elif action == 'pause':
                comm.update_workflow(workflow_id, {'status': 'paused'})
                flash('Workflow paused.', 'info')
            elif action == 'add_step':
                comm.save_step(workflow_id, {
                    'delay_days': request.form.get('delay_days') or 0,
                    'channel': request.form.get('channel') or 'email',
                    'subject': request.form.get('subject'),
                    'body': request.form.get('body'),
                })
                flash('Step added.', 'success')
            elif action == 'update_step':
                comm.save_step(workflow_id, {
                    'step_order': request.form.get('step_order'),
                    'delay_days': request.form.get('delay_days') or 0,
                    'channel': request.form.get('channel') or 'email',
                    'subject': request.form.get('subject'),
                    'body': request.form.get('body'),
                }, step_id=int(request.form.get('step_id') or 0))
                flash('Step updated.', 'success')
            elif action == 'delete_step':
                comm.delete_step(int(request.form.get('step_id') or 0))
                flash('Step removed.', 'success')
            elif action == 'enroll':
                n = comm.enroll_audience(
                    workflow_id,
                    request.form.get('audience_type') or 'all_opt_in',
                    audience_ref=request.form.get('audience_ref'),
                    audience_ids=request.form.getlist('audience_ids'),
                )
                flash(f'Enrolled {n} people into this drip.', 'success')
                log_change(_uid(), 'create', workflow_id, change_details=f'Enrolled {n} in workflow')
            elif action == 'enroll_one':
                uid = int(request.form.get('user_id') or 0)
                comm.enroll_user(workflow_id, uid)
                flash('Person enrolled.', 'success')
            elif action == 'run_due_now':
                n = comm.process_due_enrollments(limit=100)
                flash(f'Processed {n} due message(s).', 'success')
            elif action == 'scan_triggers_now':
                result = comm.run_all_auto_enrolls()
                total = sum(int(v or 0) for v in result.values())
                flash(f'Scanned triggers — {total} new enrollment(s): {result}', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('communications.workflow_detail', workflow_id=workflow_id))

    steps = comm.list_steps(workflow_id)
    enrollments = comm.list_enrollments(workflow_id)
    return render_template(
        'communications/workflow_detail.html',
        workflow=wf,
        steps=steps,
        enrollments=enrollments,
        groups=comm.list_groups_simple(),
        members=comm.list_members_for_picker(),
        audience_types=comm.AUDIENCE_TYPES,
        trigger_types=comm.TRIGGER_TYPES,
        step_channels=comm.STEP_CHANNELS,
        trigger_config=comm.parse_trigger_config(wf),
    )


@communications_bp.route('/log')
@login_required
@permission_required('send_emails')
def message_log():
    rows = comm.recent_log(150)
    for r in rows:
        if r.get('created_at'):
            r['created_fmt'] = format_church(r['created_at'], '%b %d, %Y %I:%M %p')
    return render_template('communications/log.html', rows=rows)


@communications_bp.route('/run-scheduler', methods=['POST'])
@login_required
@permission_required('send_emails')
def run_scheduler():
    """Manual kick for due campaigns + drips + automation scanners."""
    from app.utils.scheduled_emails import run_communications_jobs
    result = run_communications_jobs()
    auto = result.get('auto_enrolls') or {}
    flash(
        f"Scheduler: {result.get('campaigns', 0)} campaigns, "
        f"{result.get('drip_messages', 0)} drip messages, "
        f"{result.get('total_auto_enrolls', 0)} auto-enrolls "
        f"(visitor={auto.get('new_visitor', 0)}, member={auto.get('new_member', 0)}, "
        f"prayer={auto.get('prayer_request', 0)}, volunteer={auto.get('volunteer_onboarding', 0)}, "
        f"giving={auto.get('giving_lapsed', 0)}, follow-up={auto.get('follow_up', 0)}).",
        'success',
    )
    return redirect(request.referrer or url_for('communications.dashboard'))
