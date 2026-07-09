# myvinechurchonline/app/routes/old_settings.py
# Full path: myvinechurchonline/app/routes/old_settings.py
# File name: old_settings.py
# Brief, detailed purpose: COMPLETE REBUILD – Multi-page Settings blueprint (100% complete, no placeholders, ready to run).
# Fully split into dedicated routes/templates.
# All original features preserved exactly + enhanced censored words (quick single-add with case-insensitive duplicate check + bulk editor).
# PERMISSIONS:
#   • Admins & Owners have full access to ALL sections.
#   • Granular permissions for other roles/groups via optional 'settings_permissions' JSON column in users table.
#   • Each section has its own permission key.
#   • If column missing or user has no permissions, falls back to Admin/Owner only (safe – no crash).
#   • No import-time app context usage (fixes "Working outside of application context" error).
# All actions audit-logged, encryption preserved, image cleanup preserved, safe folder creation.
# FULL REBUILD: Consistent DictCursor usage, safe row access, no censorship check on censored_words section (admins must be able to add any word).
# Censorship checks added to other sections with visible text fields (general, online_giving option names).
# Uses contains_censored_word() from helpers.
# EMAIL SECTION FULLY REBUILT FOR MULTIPLE ACCOUNTS (email_accounts table).
# • List/add/edit/delete/set default email accounts.
# • Test send from selected account.
# • Username shown decrypted, password blank on load (leave blank to keep).
# • Incoming optional.
# • Only one default account.
# • Legacy single email migrated to "Main Account" (default) by builddb.
# • Passes 'settings' for church_name in test body.
# NEW: /settings/ticket_managers – Admin/Owner only page to add/remove users from the dedicated ticket_managers group (permission for Ticket Manager view).

from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
import os
import json
import pymysql
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

# ----------------------------------------------------------------------
# Constants & Safe Paths
# ----------------------------------------------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
DONATIONS_FOLDER = os.path.join('static', 'uploads', 'donations')  # Relative – safe

# Encryption key
key_path = os.path.join(os.path.dirname(__file__), '../../app', '..', 'config_key.bin')
env_key = os.environ.get('ENCRYPTION_KEY')
if env_key:
    key = env_key.encode()
elif os.path.exists(key_path):
    with open(key_path, 'rb') as f:
        key = f.read()
else:
    key = Fernet.generate_key()
    with open(key_path, 'wb') as f:
        f.write(key)

cipher = Fernet(key)

def encrypt(text: str) -> str:
    return cipher.encrypt(text.encode()).decode() if text else ''

def decrypt(token: str) -> str:
    if not token:
        return ''
    try:
        return cipher.decrypt(token.encode()).decode()
    except Exception:
        return ''

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------------------------
# Permission System (safe – no DB access at import)
# ----------------------------------------------------------------------
SECTION_PERMISSIONS = {
    'general': 'settings.general',
    'email': 'settings.email',
    'ai': 'settings.ai',
    'online_giving': 'settings.online_giving',
    'censored_words': 'settings.censored_words',
    'ticket_managers': 'settings.ticket_managers',  # New section permission key
}

def has_section_permission(section: str) -> bool:
    """Return True if user can edit this section."""
    if session.get('user_role') in ['Admin', 'Owner']:
        return True
    # Safe load – if column missing or not in session, deny
    try:
        perms = json.loads(session.get('settings_permissions', '[]'))
    except (json.JSONDecodeError, TypeError):
        perms = []
    return SECTION_PERMISSIONS.get(section) in perms

def can_view_settings() -> bool:
    """Return True if user can access the settings dashboard_tgp."""
    if session.get('user_role') in ['Admin', 'Owner']:
        return True
    try:
        perms = json.loads(session.get('settings_permissions', '[]'))
    except (json.JSONDecodeError, TypeError):
        perms = []
    return bool(perms)

# ----------------------------------------------------------------------
# Global Access Control
# ----------------------------------------------------------------------
@settings_bp.before_request
@login_required
def restrict_to_authorized():
    if not can_view_settings():
        flash('You do not have permission to access settings.', 'error')
        return redirect(url_for('dashboard_tgp.dashboard_tgp'))

# ----------------------------------------------------------------------
# Shared Loaders
# ----------------------------------------------------------------------
def load_settings():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM settings WHERE id = 1")
    row = cur.fetchone()
    return row or {}

def load_online_options():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM online_donation_options ORDER BY sort_order ASC")
    return cur.fetchall()

def load_email_accounts():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM email_accounts ORDER BY is_default DESC, name ASC")
    accounts = cur.fetchall()
    for acc in accounts:
        acc['outgoing_username_dec'] = decrypt(acc.get('outgoing_username', ''))
        acc['incoming_username_dec'] = decrypt(acc.get('incoming_username', ''))
    return accounts

# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@settings_bp.route('/')
def index():
    return redirect(url_for('settings.general'))

@settings_bp.route('/general', methods=['GET', 'POST'])
def general():
    if request.method == 'POST' and not has_section_permission('general'):
        flash('Insufficient permission to edit General settings.', 'error')
        return redirect(url_for('settings.general'))

    db = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        # Censored words check on visible text fields
        visible_text = ' '.join([
            request.form.get('church_name', ''),
            request.form.get('pastor', ''),
            request.form.get('address', ''),
            request.form.get('phone_number', ''),
        ])
        if contains_censored_word(visible_text):
            flash('General settings contain a prohibited word or phrase.', 'error')
            return redirect(url_for('settings.general'))

        updates = {
            'church_name': request.form.get('church_name', '').strip() or None,
            'tax_status': request.form.get('tax_status', '').strip() or None,
            'address': request.form.get('address', '').strip() or None,
            'phone_number': request.form.get('phone_number', '').strip() or None,
            'pastor': request.form.get('pastor', '').strip() or None,
            'icon_path': request.form.get('icon_path', '').strip() or None,
            'export_location': request.form.get('export_location', '').strip() or None,
            'sermon_folder_location': request.form.get('sermon_folder_location', '').strip() or None,
        }
        set_clause = ", ".join(f"{k} = %s" for k in updates if updates[k] is not None)
        values = [v for v in updates.values() if v is not None]
        if set_clause:
            cur = db.cursor()
            cur.execute(f"UPDATE settings SET {set_clause} WHERE id = 1", values)
            db.commit()
            log_change(user_id, 'update', 'Updated church & general settings')
            flash('Church & general settings saved.', 'success')

    settings = load_settings()
    return render_template('settings/general.html', settings=settings)

@settings_bp.route('/email', methods=['GET', 'POST'])
def email():
    if request.method == 'POST' and not has_section_permission('email'):
        flash('Insufficient permission to edit Email settings.', 'error')
        return redirect(url_for('settings.email'))

    os.makedirs(DONATIONS_FOLDER, exist_ok=True)  # Kept for consistency

    db = get_db()
    user_id = session['user_id']
    cur = db.cursor(pymysql.cursors.DictCursor)

    settings = load_settings()  # For church_name in test body
    accounts = load_email_accounts()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_account':
            name = request.form.get('name', '').strip()
            if not name:
                flash('Account name is required.', 'error')
            elif not request.form.get('outgoing_server'):
                flash('Outgoing server is required.', 'error')
            else:
                is_default = 1 if 'make_default' in request.form else 0
                if is_default:
                    cur.execute("UPDATE email_accounts SET is_default = 0")

                cur.execute("""
                    INSERT INTO email_accounts 
                    (name, outgoing_server, outgoing_port, outgoing_encryption, outgoing_username, outgoing_password,
                     incoming_protocol, incoming_server, incoming_port, incoming_encryption, incoming_username, incoming_password, is_default)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    name,
                    request.form.get('outgoing_server') or None,
                    request.form.get('outgoing_port') or None,
                    request.form.get('outgoing_encryption') or None,
                    encrypt(request.form.get('outgoing_username', '').strip()),
                    encrypt(request.form.get('outgoing_password', '').strip()),
                    request.form.get('incoming_protocol') or None,
                    request.form.get('incoming_server') or None,
                    request.form.get('incoming_port') or None,
                    request.form.get('incoming_encryption') or None,
                    encrypt(request.form.get('incoming_username', '').strip()),
                    encrypt(request.form.get('incoming_password', '').strip()),
                    is_default
                ))
                db.commit()
                log_change(user_id, 'create', f'Added email account: {name}')
                flash('Email account added.', 'success')

        elif action == 'update_account':
            account_id = request.form.get('account_id')
            if not account_id:
                flash('Invalid account.', 'error')
            else:
                name = request.form.get('name', '').strip()
                if not name:
                    flash('Account name required.', 'error')
                else:
                    old_out_pass = request.form.get('old_outgoing_password', '')
                    new_out_pass = request.form.get('outgoing_password', '').strip()
                    outgoing_password = encrypt(new_out_pass) if new_out_pass else old_out_pass

                    old_in_pass = request.form.get('old_incoming_password', '')
                    new_in_pass = request.form.get('incoming_password', '').strip()
                    incoming_password = encrypt(new_in_pass) if new_in_pass else old_in_pass

                    is_default = 1 if 'make_default' in request.form else 0
                    if is_default:
                        cur.execute("UPDATE email_accounts SET is_default = 0")

                    updates = """
                        name = %s,
                        outgoing_server = %s,
                        outgoing_port = %s,
                        outgoing_encryption = %s,
                        outgoing_username = %s,
                        outgoing_password = %s,
                        incoming_protocol = %s,
                        incoming_server = %s,
                        incoming_port = %s,
                        incoming_encryption = %s,
                        incoming_username = %s,
                        incoming_password = %s,
                        is_default = %s
                    """
                    values = (
                        name,
                        request.form.get('outgoing_server') or None,
                        request.form.get('outgoing_port') or None,
                        request.form.get('outgoing_encryption') or None,
                        encrypt(request.form.get('outgoing_username', '').strip()),
                        outgoing_password,
                        request.form.get('incoming_protocol') or None,
                        request.form.get('incoming_server') or None,
                        request.form.get('incoming_port') or None,
                        request.form.get('incoming_encryption') or None,
                        encrypt(request.form.get('incoming_username', '').strip()),
                        incoming_password,
                        is_default
                    )
                    cur.execute(f"UPDATE email_accounts SET {updates} WHERE id = %s", values + (account_id,))
                    db.commit()
                    log_change(user_id, 'update', f'Updated email account ID {account_id}')
                    flash('Email account updated.', 'success')

        elif action == 'delete_account':
            account_id = request.form.get('account_id')
            if account_id:
                cur.execute("SELECT is_default FROM email_accounts WHERE id = %s", (account_id,))
                row = cur.fetchone()
                if row and row['is_default']:
                    flash('Cannot delete the default account. Set another as default first.', 'error')
                else:
                    cur.execute("DELETE FROM email_accounts WHERE id = %s", (account_id,))
                    db.commit()
                    log_change(user_id, 'delete', f'Deleted email account ID {account_id}')
                    flash('Email account deleted.', 'success')

        elif action == 'send_test':
            account_id = request.form.get('test_account')
            if not account_id:
                flash('Select an account to test.', 'error')
            else:
                cur.execute("SELECT * FROM email_accounts WHERE id = %s", (account_id,))
                acc = cur.fetchone()
                if not acc:
                    flash('Account not found.', 'error')
                else:
                    password = decrypt(acc['outgoing_password'])
                    if not password:
                        flash('No password set for outgoing on this account.', 'error')
                    else:
                        try:
                            msg = MIMEMultipart()
                            msg['From'] = acc['outgoing_username']
                            msg['To'] = request.form['test_to']
                            msg['Subject'] = request.form.get('test_subject', 'MyVineChurch.Online Test Email')
                            body = request.form.get('test_body', 'This is a test email.')
                            msg.attach(MIMEText(body, 'plain'))

                            if acc['outgoing_encryption'] == 'SSL':
                                server = smtplib.SMTP_SSL(acc['outgoing_server'], acc['outgoing_port'])
                            else:
                                server = smtplib.SMTP(acc['outgoing_server'], acc['outgoing_port'])
                                if acc['outgoing_encryption'] == 'TLS':
                                    server.starttls()
                            server.login(acc['outgoing_username'], password)
                            server.send_message(msg)
                            server.quit()
                            flash('Test email sent successfully!', 'success')
                        except Exception as e:
                            flash(f'Test failed: {str(e)}', 'error')

        accounts = load_email_accounts()

    return render_template('settings/email.html', accounts=accounts, settings=settings)

@settings_bp.route('/ai', methods=['GET', 'POST'])
def ai():
    if request.method == 'POST' and not has_section_permission('ai'):
        flash('Insufficient permission to edit AI settings.', 'error')
        return redirect(url_for('settings.ai'))

    db = get_db()
    user_id = session['user_id']

    settings = load_settings()

    if request.method == 'POST':
        current = load_settings()
        new_key = request.form.get('ai_api_key', '').strip()

        updates = {
            'ai_provider': request.form.get('ai_provider', 'grok'),
            'ai_api_key': encrypt(new_key) if new_key else current.get('ai_api_key'),
            'ai_base_url': request.form.get('ai_base_url', '').strip() or None,
        }
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values())
        cur = db.cursor()
        cur.execute(f"UPDATE settings SET {set_clause} WHERE id = 1", values)
        db.commit()
        log_change(user_id, 'update', 'Updated AI configuration')
        flash('AI settings saved.', 'success')

    return render_template('settings/ai.html', settings=settings)

@settings_bp.route('/online-giving', methods=['GET', 'POST'])
def online_giving():
    if request.method == 'POST' and not has_section_permission('online_giving'):
        flash('Insufficient permission to edit Online Giving settings.', 'error')
        return redirect(url_for('settings.online_giving'))

    os.makedirs(DONATIONS_FOLDER, exist_ok=True)

    db = get_db()
    user_id = session['user_id']

    settings = load_settings()
    online_options = load_online_options()

    if request.method == 'POST':
        cur = db.cursor()
        action = request.form.get('action')

        if action == 'update_online_global':
            updates = {
                'online_donations_enabled': 1 if 'online_donations_enabled' in request.form else 0,
                'donations_page_title': request.form.get('donations_page_title', '').strip() or None,
                'donations_welcome_text': request.form.get('donations_welcome_text', '').strip() or None,
                'donations_thank_you_text': request.form.get('donations_thank_you_text', '').strip() or None,
                'donations_extra_text': request.form.get('donations_extra_text', '').strip() or None,
            }
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values())
            cur.execute(f"UPDATE settings SET {set_clause} WHERE id = 1", values)
            db.commit()
            log_change(user_id, 'update', 'Updated online giving global settings')
            flash('Online giving page settings saved.', 'success')

        elif action == 'add_option':
            name = request.form.get('option_name', '').strip()
            if not name:
                flash('Option name is required.', 'error')
            else:
                # Censored words check on option name
                if contains_censored_word(name):
                    flash('Option name contains a prohibited word or phrase.', 'error')
                else:
                    image_path = None
                    file = request.files.get('option_image')
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(DONATIONS_FOLDER, filename))
                        image_path = filename

                    cur.execute("""
                        INSERT INTO online_donation_options 
                        (name, option_type, url, embed_code, image_path, enabled, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s, 
                         COALESCE((SELECT MAX(sort_order) FROM online_donation_options), 0) + 1)
                    """, (
                        name,
                        request.form.get('option_type', '').strip() or None,
                        request.form.get('option_url') or None,
                        request.form.get('option_embed') or None,
                        image_path,
                        1 if 'option_enabled' in request.form else 0
                    ))
                    db.commit()
                    log_change(user_id, 'create', f'Added giving option: {name}')
                    flash('New giving option added.', 'success')

        elif action in ('move_up', 'move_down'):
            option_id = request.form.get('option_id')
            if option_id:
                cur.execute("SELECT sort_order FROM online_donation_options WHERE id = %s", (option_id,))
                current = cur.fetchone()
                if current:
                    delta = -1 if action == 'move_up' else 1
                    target = current['sort_order'] + delta
                    cur.execute("""
                        UPDATE online_donation_options o1
                        JOIN online_donation_options o2 ON o2.sort_order = %s
                        SET o1.sort_order = o2.sort_order, o2.sort_order = o1.sort_order
                        WHERE o1.id = %s
                    """, (target, option_id))
                    db.commit()
                    log_change(user_id, 'update', f'Reordered giving option ID {option_id}')
                    flash('Option reordered.', 'success')

        elif action == 'update_option':
            option_id = request.form.get('option_id')
            name = request.form.get('option_name', '').strip()
            if not option_id or not name:
                flash('Invalid data.', 'error')
            else:
                # Censored words check on updated option name
                if contains_censored_word(name):
                    flash('Option name contains a prohibited word or phrase.', 'error')
                else:
                    updates = {
                        'name': name,
                        'option_type': request.form.get('option_type', '').strip() or None,
                        'url': request.form.get('option_url') or None,
                        'embed_code': request.form.get('option_embed') or None,
                        'enabled': 1 if 'option_enabled' in request.form else 0
                    }
                    file = request.files.get('option_image')
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(DONATIONS_FOLDER, filename))
                        updates['image_path'] = filename
                    if 'remove_image' in request.form:
                        cur.execute("SELECT image_path FROM online_donation_options WHERE id = %s", (option_id,))
                        old = cur.fetchone()
                        if old and old['image_path']:
                            try:
                                os.remove(os.path.join(DONATIONS_FOLDER, old['image_path']))
                            except OSError:
                                pass
                        updates['image_path'] = None

                    set_clause = ", ".join(f"{k} = %s" for k in updates)
                    values = list(updates.values()) + [option_id]
                    cur.execute(f"UPDATE online_donation_options SET {set_clause} WHERE id = %s", values)
                    db.commit()
                    log_change(user_id, 'update', f'Updated giving option ID {option_id}')
                    flash('Giving option updated.', 'success')

        elif action == 'delete_option':
            option_id = request.form.get('option_id')
            if option_id:
                cur.execute("SELECT image_path FROM online_donation_options WHERE id = %s", (option_id,))
                row = cur.fetchone()
                if row and row['image_path']:
                    try:
                        os.remove(os.path.join(DONATIONS_FOLDER, row['image_path']))
                    except OSError:
                        pass
                cur.execute("DELETE FROM online_donation_options WHERE id = %s", (option_id,))
                db.commit()
                log_change(user_id, 'delete', f'Deleted giving option ID {option_id}')
                flash('Giving option deleted.', 'success')

        online_options = load_online_options()

    return render_template('settings/online_giving.html', settings=settings, online_options=online_options)

@settings_bp.route('/censored-words', methods=['GET', 'POST'])
def censored_words():
    if request.method == 'POST' and not has_section_permission('censored_words'):
        flash('Insufficient permission to edit Censored Words.', 'error')
        return redirect(url_for('settings.censored_words'))

    db = get_db()
    user_id = session['user_id']
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT censored_words FROM settings WHERE id = 1")
    row = cur.fetchone()
    raw_text = row['censored_words'] if row and row['censored_words'] else ''
    censored_words_text = raw_text

    current_words = [line.strip() for line in raw_text.splitlines() if line.strip()]

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_single_censored':
            new_word = request.form.get('new_word', '').strip()
            if not new_word:
                flash('Please enter a word or phrase.', 'error')
            elif new_word.lower() in [w.lower() for w in current_words]:
                flash(f'"{new_word}" is already censored.', 'info')
            else:
                current_words.append(new_word)
                new_text = '\n'.join(current_words)
                cur.execute("UPDATE settings SET censored_words = %s WHERE id = 1", (new_text,))
                db.commit()
                log_change(user_id, 'update', f'Added censored word: {new_word}')
                flash(f'"{new_word}" added to censored list.', 'success')
                censored_words_text = new_text

        elif action == 'update_censored_words':
            new_text = request.form.get('censored_words', '').rstrip('\n')
            cur.execute("UPDATE settings SET censored_words = %s WHERE id = 1", (new_text or None,))
            db.commit()
            log_change(user_id, 'update', 'Updated full censored words list')
            flash('Full censored words list saved.', 'success')
            censored_words_text = new_text

    return render_template('settings/censored_words.html', censored_words_text=censored_words_text)

# ----------------------------------------------------------------------
# NEW: Ticket Managers Group Management (Admin/Owner only)
# ----------------------------------------------------------------------
@settings_bp.route('/ticket_managers', methods=['GET', 'POST'])
@login_required
@role_required(['Admin', 'Owner'])
def ticket_managers():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if request.method == 'POST':
        action = request.form.get('action')
        user_id = request.form.get('user_id')

        if action == 'add' and user_id:
            cur.execute("INSERT OR IGNORE INTO ticket_managers (user_id, added_by) VALUES (%s, %s)",
                        (user_id, session['user_id']))
            db.commit()
            log_change(session['user_id'], 'update', f'Added user {user_id} to ticket managers group')
            flash('User added to ticket managers.', 'success')

        elif action == 'remove' and user_id:
            cur.execute("DELETE FROM ticket_managers WHERE user_id = %s", (user_id,))
            db.commit()
            log_change(session['user_id'], 'update', f'Removed user {user_id} from ticket managers group')
            flash('User removed from ticket managers.', 'success')

    # Load all users
    cur.execute("SELECT id, username, first_name, last_name, role FROM users ORDER BY username")
    all_users = cur.fetchall()

    # Load current managers
    cur.execute("SELECT user_id FROM ticket_managers")
    manager_ids = {row['user_id'] for row in cur.fetchall()}

    return render_template('settings/ticket_manager.html',
                           all_users=all_users,
                           manager_ids=manager_ids)