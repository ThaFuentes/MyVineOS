# Event registration + pay-now. Processor links stay outbound; paid fees hit
# donations + Accounting 4200 Event Income (not Tithes).

from __future__ import annotations

from flask import session, url_for

from app.models.db import get_db
from app.utils.time_utils import now_church
import pymysql


def event_fee(event):
    try:
        return float(event.get('cost_fees') or 0)
    except (TypeError, ValueError):
        return 0.0


def event_accepts_payment(event):
    return bool(event.get('payment_required')) or event_fee(event) > 0


def event_registration_open(event):
    if event.get('registration_open') is None:
        return True
    return bool(event.get('registration_open'))


def _selected_option_ids(event):
    raw = (event.get('payment_option_ids') or '').strip()
    if not raw:
        return None
    ids = []
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids or None


def list_giving_options(enabled_only=True):
    from werkzeug.utils import secure_filename
    from app.utils.appearance import sanitize_public_href
    from app.utils.html_sanitize import sanitize_donate_embed, sanitize_plain_text
    try:
        from app.routes.settings import load_online_options
        rows = load_online_options() or []
    except Exception:
        rows = []
    out = []
    for opt in rows:
        if enabled_only and not opt.get('enabled'):
            continue
        url = sanitize_public_href(opt.get('url') or '')
        embed = sanitize_donate_embed(opt.get('embed_code') or '')
        if not url and not embed:
            continue
        row = dict(opt)
        row['url'] = url
        row['embed_code'] = embed
        row['name'] = sanitize_plain_text(opt.get('name') or 'Online payment')
        if row.get('image_path'):
            row['image_path'] = secure_filename(str(row['image_path']))
        out.append(row)
    return out


def list_event_pay_methods(event):
    """Stripe / PayPal / Tithe.ly / custom checkout cards for this event."""
    methods = []
    from app.utils.appearance import sanitize_public_href
    custom = sanitize_public_href(event.get('payment_url') or '')
    if custom:
        methods.append({
            'id': 'custom',
            'name': 'This event checkout',
            'option_type': 'stripe',
            'url': custom,
            'embed_code': '',
            'image_path': None,
        })
    wanted = _selected_option_ids(event)
    for opt in list_giving_options(enabled_only=True):
        if wanted is not None and int(opt['id']) not in wanted:
            continue
        methods.append({
            'id': str(opt['id']),
            'name': opt.get('name') or 'Online payment',
            'option_type': (opt.get('option_type') or '').strip(),
            'url': (opt.get('url') or '').strip(),
            'embed_code': (opt.get('embed_code') or '').strip(),
            'image_path': opt.get('image_path'),
        })
    return methods


def resolve_event_payment_url(event, method_id=None):
    methods = list_event_pay_methods(event)
    if method_id:
        for m in methods:
            if str(m['id']) == str(method_id) and m.get('url'):
                return m['url']
    for m in methods:
        if m.get('url'):
            return m['url']
    try:
        return url_for(
            'public.donate',
            event_id=event.get('id'),
            amount=event_fee(event) or None,
        )
    except Exception:
        return url_for('public.donate')


def method_label(method_id, event):
    for m in list_event_pay_methods(event):
        if str(m['id']) == str(method_id):
            return m.get('name') or 'Online'
    return 'Online'


def processor_slug(method_id, event):
    for m in list_event_pay_methods(event):
        if str(m['id']) == str(method_id):
            raw = (m.get('option_type') or m.get('name') or 'online').lower()
            for key in ('stripe', 'paypal', 'venmo', 'tithely', 'tithe.ly', 'cashapp', 'zelle', 'pushpay', 'givelify'):
                if key in raw:
                    return 'tithely' if 'tithe' in key else key.replace('.', '')
            return raw[:32] or 'online'
    return 'online'


def registration_counts(event_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT
                COALESCE(SUM(quantity), 0) AS seats,
                COALESCE(SUM(CASE WHEN status IN ('paid', 'registered') THEN quantity ELSE 0 END), 0) AS taken,
                COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS paid_total,
                COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) AS pending_total
            FROM event_registrations
            WHERE event_id = %s AND status != 'cancelled'
            """,
            (event_id,),
        )
        row = cur.fetchone() or {}
        return {
            'seats': int(row.get('seats') or 0),
            'taken': int(row.get('taken') or 0),
            'paid_total': float(row.get('paid_total') or 0),
            'pending_total': float(row.get('pending_total') or 0),
        }
    except Exception:
        return {'seats': 0, 'taken': 0, 'paid_total': 0.0, 'pending_total': 0.0}


def event_is_full(event):
    cap = event.get('capacity')
    try:
        cap = int(cap) if cap else 0
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        return False
    return registration_counts(event['id'])['taken'] >= cap


def list_registrations(event_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT r.*, u.username
            FROM event_registrations r
            LEFT JOIN users u ON r.user_id = u.id
            WHERE r.event_id = %s
            ORDER BY r.created_at DESC
            """,
            (event_id,),
        )
        return cur.fetchall() or []
    except Exception:
        return []


def get_registration(reg_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM event_registrations WHERE id = %s", (reg_id,))
    return cur.fetchone()


def create_registration(event, *, name, email, quantity=1, status='pending', notes='',
                        processor='', payment_method=''):
    qty = max(1, int(quantity or 1))
    amount = round(event_fee(event) * qty, 2)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO event_registrations
                (event_id, user_id, guest_name, guest_email, quantity, amount, status, notes,
                 processor, payment_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event['id'],
                session.get('user_id'),
                (name or '').strip()[:120] or 'Guest',
                (email or '').strip()[:190] or None,
                qty,
                amount,
                status,
                (notes or '').strip()[:500] or None,
                (processor or None),
                (payment_method or None),
            ),
        )
    except Exception:
        db.rollback()
        cur.execute(
            """
            INSERT INTO event_registrations
                (event_id, user_id, guest_name, guest_email, quantity, amount, status, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event['id'],
                session.get('user_id'),
                (name or '').strip()[:120] or 'Guest',
                (email or '').strip()[:190] or None,
                qty,
                amount,
                status,
                (notes or '').strip()[:500] or None,
            ),
        )
    db.commit()
    return cur.lastrowid


def _insert_event_donation(event, reg, *, processor, method, confirmation):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if reg.get('donation_id'):
        return int(reg['donation_id'])
    try:
        cur.execute(
            "SELECT id FROM donations WHERE event_registration_id = %s LIMIT 1",
            (reg['id'],),
        )
        existing = cur.fetchone()
        if existing:
            return int(existing['id'])
    except Exception:
        pass

    gift_date = now_church().strftime('%Y-%m-%d')
    amount = float(reg.get('amount') or 0)
    if amount <= 0:
        return None
    event_name = event.get('event_name') or 'Event'
    name = (reg.get('guest_name') or 'Guest')[:200]
    notes = f"Event fee · {event_name} · qty {reg.get('quantity') or 1}"
    external_id = f"event-{event['id']}-reg-{reg['id']}"
    donor_type = 'member' if reg.get('user_id') else 'guest'
    insert = db.cursor()
    try:
        insert.execute(
            """
            INSERT INTO donations
                (name, amount, date, method, notes, confirmation_number, goods_services_provided,
                 user_id, donor_email, donor_type, source, processor, external_id,
                 event_id, event_registration_id, fund_label)
            VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,%s,'event',%s,%s,%s,%s,'Event Income')
            """,
            (
                name, amount, gift_date, method or 'Online', notes,
                confirmation or external_id, reg.get('user_id'),
                reg.get('guest_email'), donor_type, processor or 'online',
                external_id, event['id'], reg['id'],
            ),
        )
    except Exception:
        db.rollback()
        insert.execute(
            """
            INSERT INTO donations
                (name, amount, date, method, notes, confirmation_number, goods_services_provided,
                 user_id, donor_email, donor_type)
            VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,%s)
            """,
            (
                name, amount, gift_date, method or 'Online', notes,
                confirmation or external_id, reg.get('user_id'),
                reg.get('guest_email'), donor_type,
            ),
        )
    db.commit()
    donation_id = insert.lastrowid
    try:
        from app.models.accounting import post_event_income
        post_event_income(
            int(donation_id),
            amount,
            gift_date,
            memo=f"Event · {event_name} · {name}"[:500],
            created_by=session.get('user_id'),
        )
    except Exception as exc:
        print(f"event fee accounting post failed #{donation_id}: {exc}")
    return donation_id


def book_event_payment(reg_id, *, processor='', method='', confirmation=''):
    """Mark a registration paid and post one Event Income donation (idempotent)."""
    reg = get_registration(reg_id)
    if not reg:
        raise ValueError('Registration not found')
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM events WHERE id = %s", (reg['event_id'],))
    event = cur.fetchone()
    if not event:
        raise ValueError('Event not found')

    donation_id = None
    if event_fee(event) > 0:
        donation_id = _insert_event_donation(
            event, reg,
            processor=processor or reg.get('processor') or '',
            method=method or reg.get('payment_method') or 'Online',
            confirmation=confirmation or reg.get('confirmation_number') or '',
        )

    try:
        cur = db.cursor()
        cur.execute(
            """
            UPDATE event_registrations
            SET status = 'paid', donation_id = COALESCE(%s, donation_id),
                processor = COALESCE(NULLIF(%s, ''), processor),
                payment_method = COALESCE(NULLIF(%s, ''), payment_method),
                confirmation_number = COALESCE(NULLIF(%s, ''), confirmation_number)
            WHERE id = %s
            """,
            (donation_id, processor or None, method or None, confirmation or None, reg_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        cur = db.cursor()
        cur.execute("UPDATE event_registrations SET status = 'paid' WHERE id = %s", (reg_id,))
        db.commit()
    return donation_id


def cancel_registration(reg_id):
    reg = get_registration(reg_id)
    if not reg:
        return
    donation_id = reg.get('donation_id')
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE event_registrations SET status = 'cancelled' WHERE id = %s", (reg_id,))
    db.commit()
    if donation_id:
        try:
            from app.models.accounting import void_event_income
            void_event_income(int(donation_id))
        except Exception as exc:
            print(f"void event income failed #{donation_id}: {exc}")


def set_registration_status(reg_id, status):
    if status not in ('pending', 'paid', 'registered', 'cancelled'):
        raise ValueError('Invalid status')
    if status == 'paid':
        book_event_payment(reg_id)
        return
    if status == 'cancelled':
        cancel_registration(reg_id)
        return
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE event_registrations SET status = %s WHERE id = %s", (status, reg_id))
    db.commit()


def can_manage_event_registration():
    from app.utils.permissions import user_has_permission
    if session.get('user_role') in ('Staff', 'Admin', 'Owner'):
        return True
    return user_has_permission('manage_event_registration') or user_has_permission('manage_events')


def event_pay_context(event, pay_action):
    manage = can_manage_event_registration()
    methods = list_event_pay_methods(event)
    counts = registration_counts(event['id']) if event.get('id') else {}
    return {
        'event_accepts_payment': event_accepts_payment(event),
        'event_fee': event_fee(event),
        'event_registration_open': event_registration_open(event),
        'event_is_full': event_is_full(event),
        'pay_action': pay_action,
        'pay_methods': methods,
        'registrations': list_registrations(event['id']) if manage else [],
        'can_manage_regs': manage,
        'event_paid_total': counts.get('paid_total') or 0,
        'event_pending_total': counts.get('pending_total') or 0,
    }


def handle_event_pay_post(event, form):
    """Process register/pay or staff status changes. Returns a Flask redirect or None."""
    from flask import flash, redirect, request

    action = form.get('action')
    if action == 'reg_status':
        if not can_manage_event_registration():
            flash('You cannot update registrations.', 'error')
            return redirect(request.path)
        try:
            set_registration_status(int(form.get('reg_id') or 0), form.get('status'))
            flash('Registration and books updated.', 'success')
        except Exception:
            flash('Could not update that registration.', 'error')
        return redirect(request.path)

    if action != 'register_pay':
        return None

    if not event_registration_open(event):
        flash('Registration is closed.', 'error')
        return redirect(request.path)
    if event_is_full(event):
        flash('This event is full.', 'error')
        return redirect(request.path)

    name = (form.get('guest_name') or '').strip()
    if not name:
        flash('Please enter your name.', 'error')
        return redirect(request.path)
    try:
        qty = max(1, int(form.get('quantity') or 1))
    except (TypeError, ValueError):
        qty = 1

    method_id = form.get('pay_method_id') or form.get('intent')
    intent = form.get('intent') or 'pay'
    if method_id and method_id not in ('pay', 'register'):
        intent = 'pay'
    processor = processor_slug(method_id, event) if method_id not in (None, '', 'pay', 'register') else ''
    label = method_label(method_id, event) if processor else ''

    if intent == 'register' and not event.get('payment_required'):
        create_registration(
            event, name=name, email=form.get('guest_email') or '',
            quantity=qty, status='registered',
        )
        flash('You are registered for this event.', 'success')
        return redirect(request.path)

    reg_id = create_registration(
        event,
        name=name,
        email=form.get('guest_email') or '',
        quantity=qty,
        status='pending',
        processor=processor,
        payment_method=label,
    )

    pay_url = resolve_event_payment_url(event, method_id if method_id not in ('pay', 'register') else None)
    if pay_url:
        flash(
            'Your spot is saved. Finish payment with Stripe, PayPal, or the church giving page. '
            'Staff will mark it paid once the money lands — that posts Event Income to the books.',
            'success',
        )
        return redirect(pay_url)

    flash('Your registration is saved. A payment method has not been set up yet — contact the church office.', 'info')
    return redirect(request.path)
