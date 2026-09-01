# app/routes/donations/forms.py - validation for add/edit donation forms.

from flask import flash
from app.utils.helpers import contains_censored_word

DONOR_TYPES = ('member', 'guest', 'business')


def _parse_user_id(raw):
    if not raw or not str(raw).strip().isdigit():
        return None
    return int(str(raw).strip())


def _resolve_donor_type(form_data, user_id):
    if user_id:
        return 'member'
    if form_data.get('is_business'):
        return 'business'
    explicit = (form_data.get('donor_type') or '').strip().lower()
    if explicit in DONOR_TYPES:
        return explicit
    return 'guest'


def validate_add_donation_form(form_data):
    name = form_data.get('name', '').strip()
    amount_str = form_data.get('amount', '').strip()
    date = form_data.get('date', '').strip()
    method = form_data.get('method', '').strip()
    notes = form_data.get('notes', '').strip()
    confirmation_number = form_data.get('confirmation_number', '').strip()
    goods_services_provided = 1 if 'goods_services_provided' in form_data else 0
    user_id = _parse_user_id(form_data.get('user_id'))
    donor_email = form_data.get('donor_email', '').strip()
    donor_phone = form_data.get('donor_phone', '').strip()
    donor_type = _resolve_donor_type(form_data, user_id)

    if not name or not amount_str or not date or not method:
        flash('Name, Amount, Date, and Payment Method are required.', 'error')
        return None

    try:
        amount = float(amount_str)
    except ValueError:
        flash('Amount must be a valid number.', 'error')
        return None

    combined_text = f"{name} {notes} {donor_email}"
    if contains_censored_word(combined_text):
        flash('Donation record contains a prohibited word or phrase.', 'error')
        return None

    company_ein = form_data.get('company_ein', '').strip()
    if company_ein:
        ein_text = f"Company EIN: {company_ein}"
        notes = notes + ("\n" if notes else "") + ein_text

    return {
        'name': name,
        'amount': amount,
        'date': date,
        'method': method,
        'notes': notes,
        'confirmation_number': confirmation_number,
        'goods_services_provided': goods_services_provided,
        'user_id': user_id,
        'donor_email': donor_email,
        'donor_phone': donor_phone,
        'donor_type': donor_type,
    }


def validate_edit_donation_form(form_data):
    name = form_data.get('name', '').strip()
    amount_str = form_data.get('amount', '').strip()
    date = form_data.get('date', '').strip()
    method = form_data.get('method', '').strip()
    notes = form_data.get('notes', '').strip()
    confirmation_number = form_data.get('confirmation_number', '').strip()
    goods_services_provided = 1 if 'goods_services_provided' in form_data else 0
    user_id = _parse_user_id(form_data.get('user_id'))
    donor_email = form_data.get('donor_email', '').strip()
    donor_phone = form_data.get('donor_phone', '').strip()
    donor_type = _resolve_donor_type(form_data, user_id)

    if not name or not amount_str or not date or not method:
        flash('Name, Amount, Date, and Payment Method are required.', 'error')
        return None

    try:
        amount = float(amount_str)
    except ValueError:
        flash('Amount must be a valid number.', 'error')
        return None

    combined_text = f"{name} {notes} {donor_email}"
    if contains_censored_word(combined_text):
        flash('Donation record contains a prohibited word or phrase.', 'error')
        return None

    return {
        'name': name,
        'amount': amount,
        'date': date,
        'method': method,
        'notes': notes,
        'confirmation_number': confirmation_number,
        'goods_services_provided': goods_services_provided,
        'user_id': user_id,
        'donor_email': donor_email,
        'donor_phone': donor_phone,
        'donor_type': donor_type,
    }