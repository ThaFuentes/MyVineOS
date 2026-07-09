# Robust SMTP connection helper — handles port/encryption mismatches (e.g. 465+SSL vs 587+TLS).

import smtplib
from typing import Tuple


def resolve_smtp_mode(port, encryption: str) -> str:
    """
    Return connection mode: 'ssl', 'tls', or 'plain'.
    Port 465 always uses implicit SSL regardless of the stored encryption label.
    """
    port = int(port or 587)
    enc = (encryption or 'TLS').strip().upper()
    if port == 465:
        return 'ssl'
    if enc == 'SSL':
        return 'ssl'
    if enc in ('TLS', 'STARTTLS'):
        return 'tls'
    if enc == 'NONE':
        return 'plain'
    return 'tls' if port == 587 else 'plain'


def smtp_mode_label(port, encryption: str) -> str:
    mode = resolve_smtp_mode(port, encryption)
    return {'ssl': 'SSL (port 465)', 'tls': 'STARTTLS', 'plain': 'Plain'}[mode]


def smtp_connect(server: str, port, encryption: str, timeout: int = 30) -> Tuple[smtplib.SMTP, str]:
    port = int(port or 587)
    mode = resolve_smtp_mode(port, encryption)
    if mode == 'ssl':
        conn = smtplib.SMTP_SSL(server, port, timeout=timeout)
        conn.ehlo()
    else:
        conn = smtplib.SMTP(server, port, timeout=timeout)
        conn.ehlo()
        if mode == 'tls':
            conn.starttls()
            conn.ehlo()
    return conn, mode


def send_smtp_message(server: str, port, encryption: str, username: str, password: str,
                    msg, timeout: int = 30) -> str:
    """Send a message; returns the connection mode used (for user feedback)."""
    conn, mode = smtp_connect(server, port, encryption, timeout=timeout)
    try:
        if username and password:
            conn.login(username, password)
        conn.send_message(msg)
    finally:
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    return mode