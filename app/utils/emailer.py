# Secure SMTP email sender - uses email_accounts table + shared crypto/SMTP helpers.

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pymysql
from app.models.db import get_db
from app.utils.field_crypto import decrypt
from app.utils.smtp_client import send_smtp_message


def get_email_account():
    """Return the default email account or the first available one."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT name, outgoing_server, outgoing_port, outgoing_encryption,
               outgoing_username, outgoing_password
        FROM email_accounts
        WHERE is_default = 1
        LIMIT 1
    """)
    account = cur.fetchone()
    if not account:
        cur.execute("""
            SELECT name, outgoing_server, outgoing_port, outgoing_encryption,
                   outgoing_username, outgoing_password
            FROM email_accounts
            ORDER BY id ASC
            LIMIT 1
        """)
        account = cur.fetchone()
    cur.close()
    if not account or not account.get('outgoing_server'):
        raise ValueError(
            "No email account configured. Please go to Settings -> Email Accounts and add at least one account."
        )
    return account


def send_email(to_email: str, subject: str, body: str, html_body: str = None):
    """Send plain-text (and optional HTML) email using the configured default account."""
    account = get_email_account()
    username = decrypt(account['outgoing_username'])
    password = decrypt(account['outgoing_password'])
    if not username or not password:
        raise ValueError("Email account is missing username or password.")

    msg = MIMEMultipart('alternative')
    msg['From'] = username
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html'))

    send_smtp_message(
        account['outgoing_server'],
        account['outgoing_port'],
        account.get('outgoing_encryption'),
        username,
        password,
        msg,
    )