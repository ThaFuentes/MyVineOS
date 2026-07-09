# myvinechurchonline/app/routes/auth.py
# Full path: myvinechurchonline/app/routes/auth.py
# File name: auth.py
# Brief, detailed purpose: Blueprint for authentication routes (login, logout, register, password/username recovery).
# Updated for consistency: uses DictCursor everywhere.
# Register collects all form fields (phone, address, birthday, show_birthday, accepts_emails).
# First user = Owner; subsequent = pending.
# Root '/' now redirects: logged-in users → private dashboard_tgp, guests → public dashboard_tgp (the live "Gathering Place").
# This eliminates competing home pages and gives guests immediate access to church content (sermons_tgp, events_tgp, announcements_tgp).
# After successful login → private dashboard_tgp.
# Logout → public dashboard_tgp (welcoming public view).
# All routes present – fixes BuildError for request_reset_password and forgot_username.
# FULL REBUILD: Added server-side censored word check on registration for visible fields (first_name, last_name, username).
#   - If censored word detected, flash error and repopulate form (no save).
#   - Password not checked (as per requirement).
#   - Combined check on name + username for thoroughness.
#   - Form repopulation on error using request.form context.

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from app.models.db import get_db
from app.models.log import log_change
from app.utils.emailer import send_email
from app.utils.helpers import contains_censored_word
import random
import string
import pymysql

auth_bp = Blueprint('auth', __name__)


# --- Root Route (Landing Page) ---
@auth_bp.route('/')
def index():
    """
    Changed: Instead of a static landing page,
    we send guests straight to the Public Dashboard (the live "Gathering Place" with sermons_tgp, events_tgp, etc.).
    Logged-in users are sent to the private dashboard_tgp.
    This creates a single, consistent "Home" experience.
    """
    if session.get('user_id'):
        return redirect(url_for('dashboard_tgp.dashboard_tgp'))
    return redirect(url_for('public.public_dashboard'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute('SELECT COUNT(*) AS total FROM users')
    user_count = cur.fetchone()['total']

    if user_count == 0:
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')

        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()

        if not user:
            flash('Invalid credentials. Please try again.', 'error')
            return render_template('auth/login.html')

        if user['role'] == 'pending':
            flash('Your account is pending approval.', 'info')
            return render_template('auth/login.html')

        if user['role'] == 'banned':
            flash('Your account has been banned.', 'error')
            return render_template('auth/login.html')

        if check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_role'] = user['role']
            log_change(user['id'], 'login', change_details='User logged in.')
            return redirect(url_for('dashboard_tgp.dashboard_tgp'))  # Private dashboard_tgp
        else:
            flash('Invalid credentials.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        log_change(user_id, 'logout', change_details='User logged out.')
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('public.public_dashboard'))  # Welcoming public Gathering Place after logout


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute('SELECT COUNT(*) AS total FROM users')
    user_count = cur.fetchone()['total']
    is_first_user = (user_count == 0)

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        birthday = request.form.get('birthday') or None
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        accepts_emails = 1 if 'accepts_emails' in request.form else 0
        show_birthday = 1 if 'show_birthday' in request.form else 0

        # Visible fields censorship check (first_name, last_name, username)
        visible_text = f"{first_name} {last_name} {username}"
        if contains_censored_word(visible_text):
            flash('Name or username contains a prohibited word or phrase.', 'error')
            return render_template('auth/register.html', is_first_user=is_first_user, form=request.form)

        if not (first_name and last_name and email and username and password):
            flash('Required fields missing.', 'error')
            return render_template('auth/register.html', is_first_user=is_first_user, form=request.form)

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register.html', is_first_user=is_first_user, form=request.form)

        hashed_pw = generate_password_hash(password)
        role = 'Owner' if is_first_user else 'pending'
        needs_approval = 0 if is_first_user else 1

        try:
            cur.execute('''
                INSERT INTO users 
                (first_name, last_name, email, phone, address, birthday, username, password,
                 role, needs_approval, accepts_emails, show_birthday)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (first_name, last_name, email, phone, address, birthday, username, hashed_pw,
                  role, needs_approval, accepts_emails, show_birthday))
            new_id = cur.lastrowid
            db.commit()

            log_change(new_id, 'register', change_details=f"User {username} registered.")
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('auth.login'))

        except pymysql.err.IntegrityError:
            db.rollback()
            flash('Username or Email already exists.', 'error')
            return render_template('auth/register.html', is_first_user=is_first_user, form=request.form)

    return render_template('auth/register.html', is_first_user=is_first_user)


@auth_bp.route('/request-reset-password', methods=['GET', 'POST'])
def request_reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        user = cur.fetchone()

        if user:
            reset_code = ''.join(random.choices(string.digits, k=10))
            hashed_code = generate_password_hash(reset_code)
            cur.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_code, user['id']))
            db.commit()
            try:
                send_email(email, 'Password Reset - MyVineChurch.Online',
                           f'Your temporary password reset code is: {reset_code}\n\n'
                           f'Log in with this code and change your password immediately.')
                flash('Reset code sent to your email.', 'success')
            except Exception as e:
                flash('Email send failed. Contact admin.', 'error')
        else:
            flash('If the email exists, a reset code has been sent.', 'info')

        return redirect(url_for('auth.login'))

    return render_template('auth/request_reset_password.html')


@auth_bp.route('/forgot-username', methods=['GET', 'POST'])
def forgot_username():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute('SELECT username FROM users WHERE email = %s', (email,))
        user = cur.fetchone()

        if user:
            try:
                send_email(email, 'Username Recovery - MyVineChurch.Online',
                           f'Your username is: {user["username"]}')
                flash('Username sent to your email.', 'success')
            except Exception as e:
                flash('Email send failed. Contact admin.', 'error')
        else:
            flash('If the email exists, your username has been sent.', 'info')

        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_username.html')