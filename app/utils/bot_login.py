"""Mail the church bot its two keys and open a session.

The API key does not expire and goes only to the API-key inbox.
The 2FA key expires in one hour and goes only to the other inbox.
Neither secret is returned to the settings page.
"""

from __future__ import annotations

from app.utils import bot_policy as policy
from app.utils import bot_store as store


def _base_url() -> str:
    try:
        from flask import has_request_context, request
        if has_request_context():
            return (request.url_root or "").rstrip("/")
    except Exception:
        pass
    return ""


def _send(to_email: str, subject: str, body: str) -> str | None:
    try:
        from app.utils.emailer import send_email
        send_email(to_email, subject, body)
    except Exception as exc:
        print(f"bot mail: {exc}")
        return "The email did not send."
    return None


def api_mail_problem(body: str, twofa_email: str) -> str | None:
    """The permanent-key email must not carry the other inbox or a 2FA secret."""
    text = body or ""
    other = policy.normalize_email(twofa_email)
    if "twofa_key:" in text:
        return "The API key email must not include a 2FA key."
    if other and other in text.lower():
        return "The API key email must not name the 2FA inbox."
    if "api_key:" not in text or "expires: never" not in text:
        return "The API key email is missing the key."
    return None


def twofa_mail_problem(body: str, key_email: str) -> str | None:
    """The 2FA email must not carry the permanent API key or its inbox."""
    text = body or ""
    inbox = policy.normalize_email(key_email)
    if "api_key:" in text:
        return "The 2FA email must not include the API key."
    if inbox and inbox in text.lower():
        return "The 2FA email must not name the API-key inbox."
    if "twofa_key:" not in text or "expires_in:" not in text:
        return "The 2FA email is missing the key."
    return None


def create_bot(name: str, key_email: str, twofa_email: str, created_by) -> tuple[bool, str]:
    """Mail the API key first. Save the bot only after that mail sends."""
    name = (name or "").strip()[:120]
    if not name:
        return False, "Give the bot a name."
    problem = policy.inbox_problem(key_email, twofa_email)
    if problem:
        return False, problem
    key_email = policy.normalize_email(key_email)
    twofa_email = policy.normalize_email(twofa_email)
    raw, digest, prefix = policy.new_key_material()
    _subject, body = policy.api_key_mail(name, raw, _base_url())
    blocked = api_mail_problem(body, twofa_email)
    if blocked:
        return False, blocked
    if _send(key_email, _subject, body):
        return False, "The API key email did not send, so the bot was not saved."
    ok, _note = store.insert_bot(name, key_email, twofa_email, created_by, raw, digest, prefix)
    if not ok:
        return False, "The API key was emailed, but the bot could not be saved. Create it again."
    return True, (
        f"The API key was emailed to {key_email}. "
        f"Sign-in keys go to {twofa_email}. Neither secret is shown on this page."
    )


def present(raw_key: str) -> tuple[dict | None, str | None, int]:
    """Email a one-hour 2FA key. This does not open a session."""
    row = store.find_key(raw_key or "")
    if not row:
        return None, "That API key is not recognized.", 401
    if not row.get("active"):
        return None, "The owner turned this key off.", 403
    key_email = policy.normalize_email(row.get("email") or "")
    twofa_email = policy.normalize_email(row.get("twofa_email") or "")
    if policy.inbox_problem(key_email, twofa_email):
        return None, "This bot needs two different inboxes before it can sign in. The owner sets those on Bot Access.", 403
    raw, digest, _prefix = policy.new_twofa_material()
    if not store.store_twofa(int(row["id"]), digest):
        return None, "The 2FA key could not be stored.", 500
    subject, body = policy.twofa_key_mail(row.get("name") or "Bot", raw, _base_url())
    blocked = twofa_mail_problem(body, key_email)
    if blocked or raw not in body:
        store.clear_twofa(int(row["id"]))
        return None, blocked or "The 2FA email was blocked.", 500
    if _send(twofa_email, subject, body):
        store.clear_twofa(int(row["id"]))
        return None, "The 2FA email did not send. Sign in again.", 502
    return {
        "step": "twofa",
        "sent": True,
        "expires_in": policy.TWOFA_TTL_SECONDS,
        "message": (
            "A 2FA key was emailed to the other inbox. It expires in 1 hour. "
            "Send it as X-Bot-2FA to POST /api/bot/login/exchange."
        ),
    }, None, 200


def exchange(raw_key: str, raw_twofa: str) -> tuple[dict | None, str | None, int]:
    """Spend the 2FA key once and return a one-hour session token."""
    row = store.find_key(raw_key or "")
    if not row:
        return None, "That API key is not recognized.", 401
    if not row.get("active"):
        return None, "The owner turned this key off.", 403
    raw_twofa = (raw_twofa or "").strip()
    if not raw_twofa:
        return None, "Send the 2FA key as X-Bot-2FA.", 401
    status = store.twofa_matches(row, raw_twofa)
    if status == "bad":
        store.note_bad_twofa(int(row["id"]))
        return None, "That 2FA key does not match.", 401
    if status == "expired":
        return None, "That 2FA key expired. POST /api/bot/login again.", 401
    if status != "ok":
        return None, "Sign in with POST /api/bot/login first. The 2FA key is emailed then.", 401
    raw, digest, _prefix = policy.new_session_material()
    if not store.open_session(int(row["id"]), digest):
        return None, "The session could not be opened.", 500
    return {
        "step": "session",
        "session": raw,
        "token_type": "Bearer",
        "expires_in": policy.SESSION_TTL_SECONDS,
        "help": "GET /api/bot/help",
    }, None, 200


def reset_bot(key_id: int) -> tuple[bool, str]:
    """Email a new API key to the key inbox only. Do not save it if the mail fails."""
    row = store.get_key(int(key_id))
    if not row:
        return False, "That bot was not found."
    key_email = policy.normalize_email(row.get("email") or "")
    twofa_email = policy.normalize_email(row.get("twofa_email") or "")
    problem = policy.inbox_problem(key_email, twofa_email)
    if problem:
        return False, problem
    raw, digest, prefix = policy.new_key_material()
    subject, body = policy.api_key_mail(row.get("name") or "Bot", raw, _base_url())
    blocked = api_mail_problem(body, twofa_email)
    if blocked:
        return False, blocked
    if _send(key_email, subject, body):
        return False, "The API key email did not send, so the old key still works."
    ok, _note = store.replace_api_key(int(key_id), digest, prefix)
    if not ok:
        return False, "The new API key was emailed, but it could not be saved. Reset it again."
    return True, (
        f"A new API key was emailed to {key_email}. "
        "The previous key no longer works. Neither secret is shown on this page."
    )
