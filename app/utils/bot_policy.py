"""Owner switches, posting voices, and soft undo rules for the church bot.

Nothing here talks to the database. Routes and the key store call these
rules so a key can only do what the owner turned on.
"""

from __future__ import annotations

import hashlib
import json
import secrets

GREETING = "Hello. I am ready to help My Vine Church."

POST_KINDS = ("post", "quote", "verse", "blog", "book")
VISIBILITIES = ("public", "private", "personal", "followers")

# kind: write | security | read. Only these ids can be stored on a key.
SWITCHES = [
    {
        "id": "posts",
        "kind": "write",
        "group": "Wall",
        "label": "Post on the wall",
        "detail": "Verses, quotes, and other posts as the church or a person you attach.",
    },
    {
        "id": "security",
        "kind": "security",
        "group": "Security",
        "label": "Read security",
        "detail": "Recent events, ban counts, and whether security logging is still recording.",
    },
    {
        "id": "members",
        "kind": "read",
        "group": "People",
        "label": "Read members",
        "detail": "Directory names, email, phone, and role. No passwords or check-in PINs.",
    },
    {
        "id": "groups",
        "kind": "read",
        "group": "People",
        "label": "Read groups",
        "detail": "Group names and visibility.",
    },
    {
        "id": "attendance",
        "kind": "read",
        "group": "People",
        "label": "Read attendance",
        "detail": "How many people checked in on each service date.",
    },
    {
        "id": "events",
        "kind": "read",
        "group": "Church life",
        "label": "Read events",
        "detail": "Event names, dates, places, and a short description.",
    },
    {
        "id": "announcements",
        "kind": "read",
        "group": "Church life",
        "label": "Read announcements",
        "detail": "Announcement titles and a short body.",
    },
    {
        "id": "sermons",
        "kind": "read",
        "group": "Church life",
        "label": "Read the public sermon library",
        "detail": "Uploaded sermon titles and a short note. The sermon builder is its own switch.",
    },
    {
        "id": "sermon_builder",
        "kind": "sermon",
        "group": "Sermon desk",
        "label": "Sermon builder",
        "detail": "Illustrations, sermon drafts, verses, the research vault, and who is speaking on which day. The bot can draft and edit. Undo hides a draft or puts the previous words back.",
    },
    {
        "id": "prayers",
        "kind": "read",
        "group": "Church life",
        "label": "Read prayers",
        "detail": "Prayer titles and a short request.",
    },
    {
        "id": "dreams",
        "kind": "read",
        "group": "Church life",
        "label": "Read dreams",
        "detail": "Dream and vision titles and a short description.",
    },
    {
        "id": "prophecies",
        "kind": "read",
        "group": "Church life",
        "label": "Read prophecies",
        "detail": "Prophecy titles and a short description.",
    },
    {
        "id": "worship",
        "kind": "read",
        "group": "Church life",
        "label": "Read worship songs",
        "detail": "Song titles and artists. Lyrics files stay in the worship tools.",
    },
    {
        "id": "donations",
        "kind": "read",
        "group": "Office",
        "label": "Read giving",
        "detail": "Gift amounts and dates. No card numbers, and no way to add or change a gift.",
    },
    {
        "id": "bills",
        "kind": "read",
        "group": "Office",
        "label": "Read bills",
        "detail": "Bill names, amounts, and due dates. No account numbers or logins.",
    },
    {
        "id": "tickets",
        "kind": "read",
        "group": "Office",
        "label": "Read tickets",
        "detail": "Ticket titles, status, and a short description.",
    },
    {
        "id": "inventory",
        "kind": "read",
        "group": "Office",
        "label": "Read inventory",
        "detail": "Item names and stock levels.",
    },
    {
        "id": "audit",
        "kind": "read",
        "group": "Office",
        "label": "Read the change log",
        "detail": "Recent rows from the church change log.",
    },
]

# Static SELECTs only. The store binds the limit. Never add secrets here.
READS = {
    "members": (
        "SELECT id, username, first_name, last_name, email, phone, role "
        "FROM users ORDER BY id DESC LIMIT %s"
    ),
    "groups": (
        "SELECT id, name, visibility FROM groups ORDER BY id DESC LIMIT %s"
    ),
    "attendance": (
        "SELECT service_date, COUNT(*) AS people FROM attendance "
        "GROUP BY service_date ORDER BY service_date DESC LIMIT %s"
    ),
    "events": (
        "SELECT id, event_name, event_date, event_time, location, visibility, "
        "LEFT(description, 280) AS description FROM events ORDER BY id DESC LIMIT %s"
    ),
    "announcements": (
        "SELECT id, title, visibility, is_active, created_at, "
        "LEFT(content, 280) AS content FROM announcements ORDER BY id DESC LIMIT %s"
    ),
    "sermons": (
        "SELECT id, title, visibility, uploaded_at, "
        "LEFT(COALESCE(notes, details, ''), 240) AS notes "
        "FROM sermons ORDER BY id DESC LIMIT %s"
    ),
    "prayers": (
        "SELECT id, title, visibility, date_posted, "
        "LEFT(description, 280) AS description FROM prayers ORDER BY id DESC LIMIT %s"
    ),
    "dreams": (
        "SELECT id, title, category, visibility, date_posted, "
        "LEFT(description, 280) AS description FROM dreams ORDER BY id DESC LIMIT %s"
    ),
    "prophecies": (
        "SELECT id, title, visibility, created_at, "
        "LEFT(COALESCE(description, ''), 280) AS description "
        "FROM prophecies ORDER BY id DESC LIMIT %s"
    ),
    "worship": (
        "SELECT id, title, artist FROM worship_songs ORDER BY id DESC LIMIT %s"
    ),
    "donations": (
        "SELECT id, name, amount, date, method FROM donations ORDER BY id DESC LIMIT %s"
    ),
    "bills": (
        "SELECT id, bill_name, vendor_name, typical_amount, frequency, "
        "next_due_date, current_status FROM recurring_bills ORDER BY id DESC LIMIT %s"
    ),
    "tickets": (
        "SELECT id, title, status, priority, created_at, "
        "LEFT(description, 180) AS description FROM tickets ORDER BY id DESC LIMIT %s"
    ),
    "inventory": (
        "SELECT id, name, unit_of_measure, min_stock_level, typical_cost_per_unit "
        "FROM items ORDER BY id DESC LIMIT %s"
    ),
    "audit": (
        "SELECT id, user_id, action, target_id, target_username, timestamp, "
        "LEFT(COALESCE(change_details, ''), 180) AS change_details "
        "FROM change_records ORDER BY id DESC LIMIT %s"
    ),
}

CLOSED = [
    "Child check-in, bill logins, passwords, and sending email are not on this API.",
    "Deleting a post is not available. Reverse hides it and can put it back.",
    "Sermon drafts, illustrations, sections, and research notes are hidden, not deleted. A lineup change can be undone for that one date.",
    "Giving and bills are read-only. This key cannot record, edit, or pay anything.",
]


def switch_groups() -> list[dict]:
    groups = []
    for row in SWITCHES:
        if not groups or groups[-1]["name"] != row["group"]:
            groups.append({"name": row["group"], "switches": []})
        groups[-1]["switches"].append(row)
    return groups


def switch_by_id(switch_id: str) -> dict | None:
    for row in SWITCHES:
        if row["id"] == switch_id:
            return row
    return None


def default_controls() -> dict:
    return {row["id"]: False for row in SWITCHES}


def normalize_controls(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    out = default_controls()
    for row in SWITCHES:
        value = raw.get(row["id"])
        out[row["id"]] = value in (True, 1, "1", "true", "True", "on", "yes")
    return out


def switch_on(controls, switch_id: str) -> bool:
    return bool(normalize_controls(controls).get(switch_id))


def hash_key(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def new_key_material() -> tuple[str, str, str]:
    raw = "mvos_" + secrets.token_urlsafe(32)
    while raw.startswith("mvos_s_") or raw.startswith("mvos_2"):
        raw = "mvos_" + secrets.token_urlsafe(32)
    return raw, hash_key(raw), raw[:14]


def new_twofa_material() -> tuple[str, str, str]:
    raw = "mvos_2fa_" + secrets.token_urlsafe(32)
    return raw, hash_key(raw), raw[:18]


def new_session_material() -> tuple[str, str, str]:
    raw = "mvos_s_" + secrets.token_urlsafe(32)
    return raw, hash_key(raw), raw[:16]


TWOFA_TTL_SECONDS = 3600
SESSION_TTL_SECONDS = 3600


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def email_ok(value: str) -> bool:
    text = normalize_email(value)
    if len(text) < 6 or len(text) > 160 or " " in text or text.count("@") != 1:
        return False
    local, domain = text.split("@")
    return bool(local) and "." in domain and "/" not in text


def inbox_problem(key_email: str, twofa_email: str) -> str | None:
    """The API key and the 2FA key have to use two different inboxes."""
    key_email = normalize_email(key_email)
    twofa_email = normalize_email(twofa_email)
    if not email_ok(key_email):
        return "Enter the inbox that should receive the API key."
    if not email_ok(twofa_email):
        return "Enter the inbox that should receive the 2FA key."
    if key_email == twofa_email:
        return "The API key and the 2FA key need two different inboxes."
    return None


def api_key_mail(name: str, raw_key: str, base_url: str) -> tuple[str, str]:
    """Permanent key only. The 2FA inbox is not named here."""
    base = (base_url or "").rstrip("/")
    subject = "Your My Vine Church bot API key"
    body = "\n".join([
        "Hello. A My Vine Church bot API key is ready.",
        "",
        f"name: {name}",
        f"api_key: {raw_key}",
        "expires: never",
        "authorization: Bearer " + raw_key,
        f"sign_in: POST {base}/api/bot/login",
        "twofa: A separate 2FA key is emailed to the other inbox when you sign in. It expires in 1 hour. It is not in this message.",
        f"exchange: POST {base}/api/bot/login/exchange",
        "twofa_header: X-Bot-2FA",
        f"help: GET {base}/api/bot/help",
    ])
    return subject, body


def twofa_key_mail(name: str, raw_key: str, base_url: str) -> tuple[str, str]:
    """One-hour 2FA key only. The permanent API key is not included."""
    base = (base_url or "").rstrip("/")
    subject = "Your My Vine Church bot 2FA key"
    body = "\n".join([
        "Hello. Your My Vine Church bot 2FA key is ready.",
        "",
        f"name: {name}",
        f"twofa_key: {raw_key}",
        "expires: 1 hour",
        f"expires_in: {TWOFA_TTL_SECONDS}",
        "header: X-Bot-2FA",
        f"exchange: POST {base}/api/bot/login/exchange",
        "authorization: Bearer and the API key from the other inbox",
        f"help: GET {base}/api/bot/help",
    ])
    return subject, body


def person_label(row: dict | None) -> str:
    row = row or {}
    name = " ".join(
        part for part in (row.get("first_name"), row.get("last_name")) if part
    ).strip()
    username = (row.get("username") or "").strip()
    if name and username:
        return f"{name} ({username})"
    if name or username:
        return name or username
    uid = row.get("user_id") or row.get("id")
    return f"User {uid}" if uid else "Member"


def resolve_voice(token: str, voices: list[dict]) -> tuple[dict | None, str | None]:
    """Map as=church or as=user:ID onto a voice the owner attached."""
    raw = (token or "").strip().lower()
    voices = voices or []
    if raw in ("church", "as:church"):
        row = next((v for v in voices if (v.get("voice_type") or "") == "church"), None)
        if not row:
            return None, "This key cannot post as the church."
        uid = row.get("user_id")
        if not uid:
            return None, "The church voice needs an author. The owner picks that person on Bot Access."
        return {
            "posted_as": "church",
            "user_id": int(uid),
            "campus_id": 0,
            "as": "church",
        }, None
    if raw.startswith("user:"):
        part = raw.split(":", 1)[1]
        if not part.isdigit():
            return None, "Use as=user:ID with a numeric member id."
        uid = int(part)
        row = next(
            (
                v for v in voices
                if (v.get("voice_type") or "") == "user" and int(v.get("user_id") or 0) == uid
            ),
            None,
        )
        if not row:
            return None, "This key cannot post as that person."
        return {
            "posted_as": "member",
            "user_id": uid,
            "campus_id": 0,
            "as": f"user:{uid}",
        }, None
    return None, "Say which voice with as=church or as=user:ID."


def validate_post(kind: str, title: str, body: str, visibility: str) -> tuple[dict | None, str | None]:
    kind = (kind or "post").strip().lower()
    if kind not in POST_KINDS:
        return None, "kind must be post, quote, verse, blog, or book."
    title = (title or "").strip()[:255]
    body = (body or "").strip()[:8000]
    if kind in ("verse", "quote", "blog", "book") and not body:
        return None, "That kind needs a body."
    if kind == "post" and not title and not body:
        return None, "Write a title or a body."
    visibility = (visibility or "public").strip().lower()
    if visibility not in VISIBILITIES:
        visibility = "public"
    if not title:
        title = {"quote": "Quote", "verse": "Verse", "blog": "Blog", "book": "Book"}.get(kind, "Post")
    return {"kind": kind, "title": title, "body": body, "visibility": visibility}, None


# First step, then the step after it has already been reversed.
UNDO_STEPS = {
    "post.create": ("hide", "show"),
    "sermon.create": ("hide", "show"),
    "illustration.create": ("hide", "show"),
    "section.add": ("hide", "show"),
    "vault.create": ("hide", "show"),
    "sermon.update": ("restore", "reapply"),
    "section.update": ("restore", "reapply"),
    "illustration.update": ("restore", "reapply"),
    "vault.update": ("restore", "reapply"),
    "lineup.set": ("restore", "reapply"),
}

UNDO_LABELS = {
    "hide": "Hide",
    "show": "Put back",
    "restore": "Undo",
    "reapply": "Redo",
}


def undo_plan(action: str, already_reversed: bool) -> str | None:
    """Soft undo. hide sets removed_at. show clears it. Never a hard delete."""
    steps = UNDO_STEPS.get(action or "")
    if not steps:
        return None
    return steps[1] if already_reversed else steps[0]


def undo_label(action: str, already_reversed: bool) -> str | None:
    plan = undo_plan(action, already_reversed)
    if not plan:
        return None
    return UNDO_LABELS.get(plan, "Undo")


def call_map(controls) -> list[dict]:
    on = normalize_controls(controls)
    calls = [
        {"method": "GET", "path": "/api/bot/help", "switch": None,
         "about": "This map of calls, switches, and what stays closed. Send the session from exchange, not the permanent API key."},
        {"method": "POST", "path": "/api/bot/login", "switch": None,
         "about": "Send the permanent API key as Authorization: Bearer. Emails a 2FA key to the other inbox. That key expires in 1 hour. This does not open a session."},
        {"method": "POST", "path": "/api/bot/login/exchange", "switch": None,
         "about": "Send the permanent API key as Authorization: Bearer and the emailed 2FA key as X-Bot-2FA. Returns a session token that expires in 1 hour."},
        {"method": "POST", "path": "/api/bot/password-reset", "switch": None,
         "about": "While the session is open, email a new API key to the API-key inbox only. The old key and this session stop working."},
        {"method": "GET", "path": "/api/bot/whoami", "switch": None,
         "about": "Which switches and voices are on. Requires the session. GET /api/bot/me is the same."},
        {"method": "GET", "path": "/api/bot/log", "switch": None,
         "about": "What this key did, and the undo label for each change."},
        {"method": "POST", "path": "/api/bot/reverse", "switch": None,
         "about": "Undo one of this key's changes. Body: {\"log_id\": N}."},
        {"method": "POST", "path": "/api/bot/posts", "switch": "posts",
         "about": "Publish as a granted voice. Body: {\"as\":\"church\" or \"user:ID\", \"kind\":\"verse\", \"title\":\"\", \"body\":\"\"}."},
        {"method": "GET", "path": "/api/bot/posts", "switch": "posts",
         "about": "Recent live wall posts. Query: as=church or as=user:ID."},
        {"method": "GET", "path": "/api/bot/security", "switch": "security",
         "about": "Summary, recent events, events_newest_at, and recording."},
        {"method": "GET", "path": "/api/bot/sermons", "switch": "sermon_builder",
         "about": "Sermon builder drafts. ?id= or GET /api/bot/sermons/<id> opens one with its sections. ?q= searches title and passage."},
        {"method": "POST", "path": "/api/bot/sermons", "switch": "sermon_builder",
         "about": "Start a draft. Body: {\"title\":\"\", \"primary_passage\":\"\", \"preacher_id\": N, \"service_date\":\"YYYY-MM-DD\", \"notes\":\"\"}."},
        {"method": "POST", "path": "/api/bot/sermons/<id>", "switch": "sermon_builder",
         "about": "Change a draft's title, passage, preacher, date, notes, or conclusion. GET reads that draft."},
        {"method": "POST", "path": "/api/bot/sermons/<id>/sections", "switch": "sermon_builder",
         "about": "Add a section, or change one when section_id is set. Body: {\"section_type\":\"point\", \"title\":\"\", \"content\":\"\"} or {\"illustration_id\": N} or {\"reference\":\"John 3:16\"}."},
        {"method": "GET", "path": "/api/bot/illustrations", "switch": "sermon_builder",
         "about": "Illustration library, including private stories. ?q= searches. ?id= opens one."},
        {"method": "POST", "path": "/api/bot/illustrations", "switch": "sermon_builder",
         "about": "Save an illustration. Body: {\"title\":\"\", \"content\":\"\", \"source\":\"\", \"tags\":\"\"}."},
        {"method": "POST", "path": "/api/bot/illustrations/<id>", "switch": "sermon_builder",
         "about": "Change an illustration's title, story, source, or tags."},
        {"method": "GET", "path": "/api/bot/vault", "switch": "sermon_builder",
         "about": "Sermon research vault. Shared notes plus this owner's private notes. ?q= searches. ?id= opens one."},
        {"method": "POST", "path": "/api/bot/vault", "switch": "sermon_builder",
         "about": "Save a research note. Body: {\"title\":\"\", \"content\":\"\", \"scripture_reference\":\"\"}."},
        {"method": "POST", "path": "/api/bot/vault/<id>", "switch": "sermon_builder",
         "about": "Change a research note the key can already see."},
        {"method": "GET", "path": "/api/bot/verses", "switch": "sermon_builder",
         "about": "Look up scripture. Query: ref=John 3:16 or ref=Romans 8:28-30."},
        {"method": "GET", "path": "/api/bot/lineup", "switch": "sermon_builder",
         "about": "Who is speaking, and which sermon, on upcoming service days. Query: days=21."},
        {"method": "POST", "path": "/api/bot/lineup", "switch": "sermon_builder",
         "about": "Set the speaker or sermon for one date. Body: {\"date\":\"YYYY-MM-DD\", \"preacher_id\": N, \"sermon_id\": N}. One Sunday only, not every week."},
    ]
    for row in SWITCHES:
        if row["kind"] != "read":
            continue
        calls.append({
            "method": "GET",
            "path": f"/api/bot/read/{row['id']}",
            "switch": row["id"],
            "about": row["detail"],
        })
    for call in calls:
        need = call["switch"]
        call["allowed"] = True if need is None else bool(on.get(need))
    return calls


def help_payload(controls, voices: list[dict] | None = None) -> dict:
    calls = call_map(controls)
    lines = []
    for call in calls:
        mark = "on" if call["allowed"] else "off"
        lines.append(f"{call['method']} {call['path']} [{mark}] {call['about']}")
    voice_rows = []
    for voice in voices or []:
        kind = voice.get("voice_type") or ""
        if kind == "church":
            voice_rows.append({"as": "church", "author_user_id": voice.get("user_id"), "label": voice.get("label") or "Church"})
        elif kind == "user" and voice.get("user_id"):
            voice_rows.append({
                "as": f"user:{int(voice['user_id'])}",
                "author_user_id": int(voice["user_id"]),
                "label": voice.get("label") or person_label(voice),
            })
    return {
        "lines": lines,
        "calls": calls,
        "switches": normalize_controls(controls),
        "voices": voice_rows,
        "closed": list(CLOSED),
        "undo": "POST /api/bot/reverse with {\"log_id\": N} hides a post, sermon draft, illustration, or section, or puts the previous text back. The row is kept.",
        "sign_in": {
            "api_key": "Does not expire. Emailed only to the API-key inbox. Never shown on the dashboard.",
            "twofa_key": "Expires in 1 hour. Emailed only to the other inbox by POST /api/bot/login.",
            "session": "POST /api/bot/login/exchange returns session. Send it as Authorization: Bearer on every other call. It expires in 1 hour.",
            "twofa_header": "X-Bot-2FA",
            "expires_in": TWOFA_TTL_SECONDS,
        },
    }
