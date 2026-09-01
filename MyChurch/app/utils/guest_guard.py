# Stop automated guest posts without bothering signed-in members.

from __future__ import annotations

import random
import time
from collections import defaultdict, deque

from flask import flash, request, session

GUEST_POST_ACTIONS = frozenset({
    'comment',
    'reply',
    'submit_request',
    'submit_dream',
    'submit_prophecy',
})

_HONEYPOT_FIELDS = ('website', 'company_url', 'fax_number')
_MIN_SECONDS = 1.0
_RATE_WINDOW = 15 * 60
_RATE_MAX = 8
_ip_hits: dict[str, deque] = defaultdict(deque)


def guest_is_signed_in() -> bool:
    return bool(session.get('user_id'))


def issue_guest_challenge() -> tuple[int, int]:
    a = session.get('guest_captcha_a')
    b = session.get('guest_captcha_b')
    if isinstance(a, int) and isinstance(b, int):
        return a, b
    a, b = random.randint(2, 9), random.randint(2, 9)
    session['guest_captcha_a'] = a
    session['guest_captcha_b'] = b
    session['guest_captcha_issued'] = time.time()
    return a, b


def guest_challenge_context() -> dict:
    if guest_is_signed_in():
        return {'show_guest_captcha': False, 'guest_captcha_a': None, 'guest_captcha_b': None}
    a, b = issue_guest_challenge()
    return {'show_guest_captcha': True, 'guest_captcha_a': a, 'guest_captcha_b': b}


def _too_many_from_ip(ip: str) -> bool:
    now = time.time()
    hits = _ip_hits[ip]
    while hits and now - hits[0] > _RATE_WINDOW:
        hits.popleft()
    if len(hits) >= _RATE_MAX:
        return True
    hits.append(now)
    return False


def allow_guest_post(form) -> bool:
    """True if this POST may proceed. Signed-in members always pass."""
    if guest_is_signed_in():
        return True

    for field in _HONEYPOT_FIELDS:
        if (form.get(field) or '').strip():
            flash('Could not submit that request.', 'error')
            return False

    issued = float(session.get('guest_captcha_issued') or 0)
    if issued and (time.time() - issued) < _MIN_SECONDS:
        flash('Please wait a moment and try again.', 'error')
        return False

    a = session.get('guest_captcha_a')
    b = session.get('guest_captcha_b')
    raw = str(form.get('guest_captcha') or '').strip()
    try:
        answer = int(raw)
    except ValueError:
        answer = None
    if not isinstance(a, int) or not isinstance(b, int) or answer != a + b:
        flash('Please answer the quick check so we know you are a person.', 'error')
        issue_guest_challenge()
        return False

    ip = (request.remote_addr or 'unknown').strip()
    if _too_many_from_ip(ip):
        flash('Too many posts from this connection. Please wait a bit and try again.', 'error')
        return False

    session.pop('guest_captcha_a', None)
    session.pop('guest_captcha_b', None)
    session.pop('guest_captcha_issued', None)
    return True


def should_guard_public_post() -> bool:
    if request.method != 'POST' or guest_is_signed_in():
        return False
    action = (request.form.get('action') or '').strip()
    return action in GUEST_POST_ACTIONS
