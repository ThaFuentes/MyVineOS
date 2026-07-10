from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from . import auth_bp
from .queries import (
    get_total_user_count,
    get_user_by_username,
    get_user_by_email,
    get_user_by_verification_token,
    create_new_user,
    update_user_password,
    mark_email_verified,
    set_verification_token,
    get_unverified_user_by_email,
    count_pending_registrations,
)
from .forms import (
    validate_register_form,
    validate_password_reset_form,
    validate_forgot_username_form,
)
from .utils import generate_reset_code
from app.models.log import log_change
from app.models.users import approve_user
from app.utils.emailer import send_email
from app.utils.welcome_page import render_welcome_page
from app.utils.email_notifications import (
    get_notification_settings,
    generate_verification_token,
    send_registration_admin_alert,
    send_email_verification,
    send_registration_welcome,
)
from app.utils.totp_auth import verify_totp_code, decrypt_totp_secret
from app.utils.account_moderation import is_account_login_locked

try:
    from poweredbytop.auth.session import mark_as_vetted, record_login_attempt, is_locked_out
except Exception:
    def mark_as_vetted():
        pass

    def record_login_attempt(success: bool):
        pass

    def is_locked_out():
        return False


def _complete_login(user):
    """
    Establish a logged-in session on THIS device only.
    Other devices keep their own cookies — multi-device concurrent login is allowed.
    session.clear() only rewrites the current browser's cookie, not other devices.
    """
    record_login_attempt(True)
    # Reset only this browser cookie (avoids carrying guest CSRF / lockout junk).
    # Does NOT invalidate phone/tablet/desktop sessions for the same account.
    session.clear()
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['user_role'] = user['role']
    session['is_shadow_banned'] = bool(user.get('is_shadow_banned'))
    session.pop('pending_2fa_user_id', None)
    try:
        from app.utils.ui_prefs import apply_ui_prefs_to_session
        apply_ui_prefs_to_session(session, user_row=user)
    except Exception:
        session['user_theme'] = 'cyan-glow'
        session['ui_font_scale'] = 'md'
        session['bible_font_scale'] = 'md'
    log_change(
        user['id'],
        'login',
        change_details='User logged in (multi-device sessions allowed).',
    )
    mark_as_vetted()
    session.modified = True
    return redirect(url_for('dashboard.dashboard'))


def _login_blocked_reason(user):
    """Return a human message if login should be refused, else None.
    Second value is optional redirect kwargs for resend-verification.
    """
    if user['role'] == 'pending':
        return 'Your account is pending approval by church leadership.', None
    if user['role'] == 'banned':
        return 'Your account has been banned.', None
    if is_account_login_locked(user):
        return 'Your account is temporarily locked. Contact church leadership for assistance.', None
    settings = get_notification_settings()
    if settings['registration_require_email_verification'] and not user.get('email_verified'):
        if user['role'] != 'Owner':
            email = (user.get('email') or '').strip()
            msg = (
                'Please verify your email address before logging in. '
                'Use "Resend email verification" on the login page if you need a new link.'
            )
            return msg, {'email': email} if email else None
    return None, None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if is_locked_out():
            flash('Too many failed login attempts. Please wait a few minutes and try again.', 'error')
            return render_template('auth/login.html')

        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')
        user = get_user_by_username(username)
        if not user or not check_password_hash(user['password'], password):
            record_login_attempt(False)
            flash('Invalid credentials.', 'error')
            return render_template('auth/login.html')

        blocked, resend_kw = _login_blocked_reason(user)
        if blocked:
            flash(blocked, 'info' if user['role'] == 'pending' else 'error')
            # Unverified email: send them to resend page with email prefilled
            if resend_kw is not None:
                return redirect(url_for('auth.resend_verification', **resend_kw))
            return render_template('auth/login.html')

        if user.get('totp_enabled'):
            session['pending_2fa_user_id'] = user['id']
            return redirect(url_for('auth.login_2fa'))

        return _complete_login(user)
    return render_template('auth/login.html')


@auth_bp.route('/login/2fa', methods=['GET', 'POST'])
def login_2fa():
    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))

    from app.models.users import get_user_by_id
    user = get_user_by_id(user_id)
    if not user or not user.get('totp_enabled'):
        session.pop('pending_2fa_user_id', None)
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('totp_code', '').strip()
        secret = decrypt_totp_secret(user.get('totp_secret') or '')
        if verify_totp_code(secret, code):
            return _complete_login(user)
        record_login_attempt(False)
        flash('Invalid authentication code. Try again.', 'error')

    return render_template('auth/login_2fa.html', username=user.get('username'))


@auth_bp.route('/logout')
def logout():
    """Log out THIS device only. Other devices stay signed in."""
    user_id = session.get('user_id')
    if user_id:
        log_change(user_id, 'logout', change_details='User logged out (this device only).')
    session.clear()
    flash('You have been logged out on this device.', 'info')
    return redirect(url_for('public.public_dashboard.public_dashboard'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    total_users = get_total_user_count()
    is_first_user = (total_users == 0)
    notif_settings = get_notification_settings()

    if request.method == 'POST':
        clean_data = validate_register_form(request.form)
        if not clean_data:
            return render_template(
                'auth/register.html',
                is_first_user=is_first_user,
                form=request.form,
                notif_settings=notif_settings,
            )

        hashed_pw = generate_password_hash(clean_data['password'])
        verify_token = None
        email_verified = 1

        if is_first_user:
            role = 'Owner'
            needs_approval = 0
        elif notif_settings['registration_auto_approve']:
            role = 'Member'
            needs_approval = 0
        else:
            role = 'pending'
            needs_approval = 1

        if not is_first_user and notif_settings['registration_require_email_verification']:
            email_verified = 0
            verify_token = generate_verification_token()

        try:
            new_id = create_new_user(
                first_name=clean_data['first_name'],
                last_name=clean_data['last_name'],
                email=clean_data['email'],
                phone=clean_data['phone'],
                address=clean_data['address'],
                birthday=clean_data['birthday'],
                username=clean_data['username'],
                hashed_password=hashed_pw,
                role=role,
                needs_approval=needs_approval,
                accepts_emails=clean_data['accepts_emails'],
                show_birthday=clean_data['show_birthday'],
                email_verified=email_verified,
                email_verification_token=verify_token,
            )
            user_row = {
                'id': new_id,
                'username': clean_data['username'],
                'first_name': clean_data['first_name'],
                'last_name': clean_data['last_name'],
                'email': clean_data['email'],
                'role': role,
            }
            log_change(new_id, 'register', change_details=f"User {clean_data['username']} registered.")

            if verify_token:
                try:
                    send_email_verification(new_id, clean_data['email'], verify_token, clean_data['username'])
                except Exception:
                    flash('Account created but verification email could not be sent. Contact an admin.', 'error')
                    return redirect(url_for('auth.login'))

            if role == 'Member' and email_verified:
                try:
                    send_registration_welcome(clean_data['email'], clean_data['username'])
                except Exception:
                    pass

            try:
                send_registration_admin_alert(user_row)
            except Exception:
                pass

            if verify_token:
                flash('Registration successful! Check your email to verify your account before logging in.', 'success')
            elif role == 'pending':
                flash('Registration submitted. An administrator will review your account.', 'success')
            else:
                flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('auth.login'))

        except Exception:
            flash('Username or Email already exists.', 'error')
            return render_template(
                'auth/register.html',
                is_first_user=is_first_user,
                form=request.form,
                notif_settings=notif_settings,
            )
    return redirect(url_for('auth.login', tab='register'))


@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    """Public form: send a fresh verification email to an unverified account."""
    prefill = (request.args.get('email') or request.form.get('email') or '').strip()

    if request.method == 'POST':
        email = prefill.lower()
        if not email:
            flash('Enter your registration email address.', 'error')
            return render_template('auth/resend_verification.html', email=prefill)

        settings = get_notification_settings()
        if not settings.get('registration_require_email_verification'):
            flash('Email verification is not required on this site. You can try logging in.', 'info')
            return redirect(url_for('auth.login'))

        user = get_unverified_user_by_email(email)
        if user:
            token = generate_verification_token()
            set_verification_token(user['id'], token)
            sent = False
            try:
                sent = bool(send_email_verification(
                    user['id'], email, token, user.get('username') or email,
                ))
            except Exception:
                sent = False
            if not sent:
                flash(
                    'Could not send the verification email. '
                    'Check that site email (SMTP) is configured, or contact an admin.',
                    'error',
                )
                return render_template('auth/resend_verification.html', email=prefill)

        # Same message whether or not the address matched (avoid account enumeration)
        flash(
            'If that email is registered and not yet verified, a new verification link has been sent. '
            'Check your inbox and spam folder.',
            'success',
        )
        return redirect(url_for('auth.login'))

    return render_template('auth/resend_verification.html', email=prefill)


@auth_bp.route('/verify-email/<token>', methods=['GET', 'POST'])
def verify_email(token):
    from urllib.parse import unquote
    token = unquote(token or '').strip()
    user = get_user_by_verification_token(token)
    if not user:
        flash('Invalid or expired verification link. You can request a new one below.', 'error')
        return render_template('auth/verify_email.html', success=False)

    if user.get('email_verified'):
        flash('Your email is already verified. You can log in once your account is approved.', 'info')
        return render_template('auth/verify_email.html', success=True, already=True)

    if request.method == 'POST':
        mark_email_verified(user['id'])
        log_change(user['id'], 'email_verified', change_details='Email address verified.')
        try:
            if user.get('email') and user.get('role') != 'pending':
                send_registration_welcome(user['email'], user['username'], 'Your email is now verified.')
        except Exception:
            pass
        flash('Email verified! You can now log in (if your account has been approved).', 'success')
        return render_template('auth/verify_email.html', success=True)

    return render_template(
        'auth/verify_email_confirm.html',
        token=token,
        username=user.get('username') or 'there',
    )


@auth_bp.route('/request-reset-password', methods=['GET', 'POST'])
def request_reset_password():
    if request.method == 'POST':
        email = validate_password_reset_form(request.form)
        if not email:
            return render_template('auth/request_reset_password.html')
        user = get_user_by_email(email)
        if user:
            reset_code = generate_reset_code()
            hashed_code = generate_password_hash(reset_code)
            try:
                update_user_password(user['id'], hashed_code)
                send_email(email, 'Password Reset - MyVineChurch.Online',
                           f'Your temporary password reset code is: {reset_code}\n\n'
                           f'Log in with this code and change your password immediately.')
                flash('Reset code sent to your email.', 'success')
            except Exception:
                flash('Email send failed. Contact admin.', 'error')
        else:
            flash('If the email exists, a reset code has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/request_reset_password.html')


@auth_bp.route('/forgot-username', methods=['GET', 'POST'])
def forgot_username():
    if request.method == 'POST':
        email = validate_forgot_username_form(request.form)
        if not email:
            return render_template('auth/forgot_username.html')
        user = get_user_by_email(email)
        if user:
            try:
                send_email(email, 'Username Recovery - MyVineChurch.Online',
                           f'Your username is: {user["username"]}')
                flash('Username sent to your email.', 'success')
            except Exception:
                flash('Email send failed. Contact admin.', 'error')
        else:
            flash('If the email exists, your username has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_username.html')


@auth_bp.route('/index')
def auth_index():
    return render_welcome_page()