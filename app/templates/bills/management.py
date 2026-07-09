# app/routes/bills/management.py
# Full path: MyVineChurch/app/routes/bills/management.py
# File name: management.py
# Brief, detailed purpose: Add and Edit bill routes.
# Uses centralized encryption from app.models.credentials.
# Never shows saved password in edit form.
# Full censorship + audit logging.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
from app.models.credentials import encrypt_credential, decrypt_credential
from itertools import zip_longest
import pymysql
import json
from app.utils.time_utils import utc_now

def register_management_routes(bp):
    @bp.route('/add', methods=['GET', 'POST'])
    @login_required
    @role_required(['Staff', 'Admin', 'Owner'])
    def add_bill():
        if request.method == 'GET':
            return render_template('bills/edit_bill.html', bill=None, additional_links=[])

        # POST
        bill_name = request.form.get('bill_name', '').strip()
        if not bill_name:
            flash('Bill name is required.', 'error')
            links = [{"label": l.strip(), "url": u.strip()} for l, u in zip_longest(
                request.form.getlist('link_label'), request.form.getlist('link_url')) if l.strip() or u.strip()]
            return render_template('bills/edit_bill.html', bill=None, additional_links=links)

        # Censorship check
        combined_text = f"{bill_name} {request.form.get('vendor_name', '')} {request.form.get('description', '')} " \
                        f"{request.form.get('notes', '')}"
        if contains_censored_word(combined_text):
            flash('Entry contains a prohibited word or phrase.', 'error')
            links = [{"label": l.strip(), "url": u.strip()} for l, u in zip_longest(
                request.form.getlist('link_label'), request.form.getlist('link_url')) if l.strip() or u.strip()]
            return render_template('bills/edit_bill.html', bill=None, additional_links=links)

        # Prepare links
        link_labels = request.form.getlist('link_label')
        link_urls = request.form.getlist('link_url')
        links = [{"label": l.strip(), "url": u.strip()} for l, u in zip_longest(link_labels, link_urls) if l.strip() or u.strip()]
        links_json = json.dumps(links) if links else None

        # Encrypt credentials using centralized model
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        encrypted_username = encrypt_credential(username) if username else None
        encrypted_password = encrypt_credential(password) if password else None

        values = (
            bill_name,
            request.form.get('vendor_name'),
            request.form.get('description'),
            request.form.get('typical_amount') or None,
            request.form.get('account_number'),
            request.form.get('customer_number'),
            request.form.get('phone1'),
            request.form.get('phone2'),
            request.form.get('address'),
            request.form.get('payment_url'),
            request.form.get('login_url'),
            links_json,
            encrypted_username,
            encrypted_password,
            request.form.get('frequency', 'monthly'),
            request.form.get('due_day') or None,
            request.form.get('due_month') or None,
            request.form.get('reminder_days_before', 7),
            request.form.get('next_due_date'),
            request.form.get('current_status', 'pending'),
            request.form.get('notes'),
            session['user_id'],  # created_by
            session['user_id'],  # updated_by
            utc_now()            # updated_at
        )

        try:
            db = get_db()
            cur = db.cursor()
            cur.execute("""
                INSERT INTO recurring_bills (
                    bill_name, vendor_name, description, typical_amount, account_number, customer_number,
                    phone1, phone2, address, payment_url, login_url, additional_links,
                    encrypted_username, encrypted_password, frequency, due_day, due_month,
                    reminder_days_before, next_due_date, current_status, notes,
                    created_by, updated_by, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, values)
            db.commit()
            bill_id = cur.lastrowid
            log_change(session['user_id'], 'create_bill', bill_id, bill_name, 'Created recurring bill')
            flash('Recurring bill added successfully.', 'success')
            return redirect(url_for('bills.bills'))
        except Exception as exc:
            db.rollback()
            flash('Failed to add bill.', 'error')
            print(f"Add bill error: {exc}")
            return render_template('bills/edit_bill.html', bill=None, additional_links=links)

    @bp.route('/edit/<int:bill_id>', methods=['GET', 'POST'])
    @login_required
    @role_required(['Staff', 'Admin', 'Owner'])
    def edit_bill(bill_id):
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT * FROM recurring_bills WHERE id = %s", (bill_id,))
        bill = cur.fetchone()

        if not bill:
            flash('Bill not found.', 'error')
            return redirect(url_for('bills.bills'))

        if request.method == 'POST':
            bill_name = request.form.get('bill_name', '').strip()
            if not bill_name:
                flash('Bill name is required.', 'error')
                return render_template('bills/edit_bill.html', bill=bill, additional_links=[])

            # Censorship check
            combined_text = f"{bill_name} {request.form.get('vendor_name', '')} {request.form.get('description', '')}"
            if contains_censored_word(combined_text):
                flash('Entry contains a prohibited word or phrase.', 'error')
                return render_template('bills/edit_bill.html', bill=bill, additional_links=[])

            # Prepare links
            link_labels = request.form.getlist('link_label')
            link_urls = request.form.getlist('link_url')
            links = [{"label": l.strip(), "url": u.strip()} for l, u in zip_longest(link_labels, link_urls) if l.strip() or u.strip()]
            links_json = json.dumps(links) if links else None

            # Encrypt credentials (only if new value provided)
            username_input = request.form.get('username', '').strip()
            password_input = request.form.get('password', '').strip()

            encrypted_username = encrypt_credential(username_input) if username_input else bill['encrypted_username']
            encrypted_password = encrypt_credential(password_input) if password_input else bill['encrypted_password']

            try:
                cur.execute("""
                    UPDATE recurring_bills SET
                        bill_name = %s, vendor_name = %s, description = %s, typical_amount = %s,
                        account_number = %s, customer_number = %s, phone1 = %s, phone2 = %s,
                        address = %s, payment_url = %s, login_url = %s, additional_links = %s,
                        encrypted_username = %s, encrypted_password = %s, frequency = %s,
                        due_day = %s, due_month = %s, reminder_days_before = %s,
                        next_due_date = %s, current_status = %s, notes = %s,
                        updated_by = %s, updated_at = %s
                    WHERE id = %s
                """, (
                    bill_name, request.form.get('vendor_name'), request.form.get('description'),
                    request.form.get('typical_amount') or None,
                    request.form.get('account_number'), request.form.get('customer_number'),
                    request.form.get('phone1'), request.form.get('phone2'),
                    request.form.get('address'), request.form.get('payment_url'),
                    request.form.get('login_url'), links_json,
                    encrypted_username, encrypted_password,
                    request.form.get('frequency', 'monthly'),
                    request.form.get('due_day') or None,
                    request.form.get('due_month') or None,
                    request.form.get('reminder_days_before', 7),
                    request.form.get('next_due_date'),
                    request.form.get('current_status', 'pending'),
                    request.form.get('notes'), session['user_id'], utc_now(), bill_id
                ))
                db.commit()
                log_change(session['user_id'], 'update_bill', bill_id, bill_name, 'Updated recurring bill')
                flash('Bill updated successfully.', 'success')
                return redirect(url_for('bills.view_bill', bill_id=bill_id))
            except Exception as exc:
                db.rollback()
                flash('Failed to update bill.', 'error')
                print(f"Edit bill error: {exc}")
                return render_template('bills/edit_bill.html', bill=bill, additional_links=links)

        # GET - decrypt username safely (never show password)
        bill['username'] = decrypt_credential(bill.get('encrypted_username'))
        bill['password'] = ''  # Never pre-fill password for security

        bill['links'] = json.loads(bill.get('additional_links') or '[]')

        return render_template('bills/edit_bill.html', bill=bill, additional_links=bill['links'])