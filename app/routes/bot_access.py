"""Owner Bot Access page and the /api/bot key.

The owner turns each switch on or off and attaches voices. The key can post
as those voices, read the areas that are on, and hide or restore its own posts.
"""

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app.models.users import get_user_by_id
from app.utils import bot_policy as policy
from app.utils import bot_sermons as sermons
from app.utils import bot_store as store
from app.utils.decorators import login_required

bot_access_bp = Blueprint("bot_access", __name__)


def _json(ok: bool, data=None, error: str | None = None, status: int = 200):
    body = {"ok": ok, "greeting": policy.GREETING}
    if error:
        body["error"] = error
    if data is not None:
        body["data"] = data
    return jsonify(body), status


def _bearer() -> str:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.headers.get("X-Bot-Key") or "").strip()


def _owner_user():
    uid = session.get("user_id")
    if not uid:
        return None
    user = get_user_by_id(uid)
    if not user or (user.get("role") or "") != "Owner":
        return None
    return user


def _require_key():
    raw = _bearer()
    if not raw:
        return None, _json(False, error="Send the key as Authorization: Bearer mvos_…", status=401)
    row = store.find_key(raw)
    if not row:
        return None, _json(False, error="That key is not recognized.", status=401)
    if not row.get("active"):
        return None, _json(False, error="The owner turned this key off.", status=403)
    return row, None


def _need(row: dict, switch_id: str):
    if policy.switch_on(row.get("controls"), switch_id):
        return None
    label = (policy.switch_by_id(switch_id) or {}).get("label") or switch_id
    store.write_log(int(row["id"]), "denied", ok=False, detail=f"{switch_id} is off", target_type="switch")
    return _json(False, error=f"The owner has {label} turned off for this key.", status=403)


def _payload():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict):
            return data
    return request.form


def _security_payload() -> dict:
    summary = {}
    events = []
    total = 0
    newest = None
    recording = False
    try:
        from app.routes.security.queries import list_security_events, summary_stats
        summary = summary_stats() or {}
        events, total = list_security_events(limit=30)
        recording = True
    except Exception as exc:
        print(f"bot security: {exc}")
        events, total = [], 0
    clean = []
    for row in events or []:
        item = {}
        for key, val in (row or {}).items():
            item[key] = store._cell(val)
        if item.get("timestamp") and not newest:
            newest = item["timestamp"]
        clean.append(item)
    for key, val in list(summary.items()):
        summary[key] = store._cell(val)
    return {
        "summary": summary,
        "events": clean,
        "events_total": total,
        "events_newest_at": newest,
        "recording": recording,
    }


def _apply_reverse(entry: dict, actor: str) -> tuple[bool, str]:
    plan = policy.undo_plan(entry.get("action") or "", bool(entry.get("reversed")))
    if plan is None or not entry.get("ok"):
        return False, "That entry cannot be reversed."
    action = entry.get("action") or ""
    if action == "post.create":
        post_id = entry.get("target_id") or (entry.get("snapshot") or {}).get("post_id")
        if not post_id:
            return False, "That entry has no post to hide or restore."
        ok, message = store.set_post_removed(int(post_id), plan == "hide")
    else:
        ok, message = sermons.apply_undo(plan, entry)
    if not ok:
        return False, message
    store.mark_reversed(int(entry["id"]), actor, clear=plan in ("show", "reapply"))
    return True, message


def _desk():
    row, err = _require_key()
    if err:
        return None, err
    denied = _need(row, "sermon_builder")
    if denied:
        return None, denied
    return row, None


def _actor_id(row: dict) -> int | None:
    try:
        uid = int(row.get("created_by") or 0)
    except (TypeError, ValueError):
        uid = 0
    return uid or None


def _finish(row: dict, result: dict):
    if not result.get("ok"):
        if result.get("status") == 500 and result.get("action"):
            store.write_log(
                int(row["id"]),
                result.get("action") or "sermon",
                ok=False,
                detail=result.get("error") or "",
            )
        return _json(False, error=result.get("error") or "That did not work.", status=result.get("status") or 400)
    data = dict(result.get("data") or {})
    log = result.get("log")
    if log:
        log_id = store.write_log(
            int(row["id"]),
            log.get("action") or "sermon",
            ok=True,
            detail=log.get("detail") or "",
            target_type=log.get("target_type"),
            target_id=log.get("target_id"),
            snapshot=log.get("snapshot"),
        )
        data["log_id"] = log_id
        data["undo"] = "POST /api/bot/reverse with this log_id."
    return _json(True, data)


def _needs_owner(row: dict, what: str):
    actor = _actor_id(row)
    if actor:
        return actor, None
    return None, _json(False, error=f"This key has no owner on it, so it cannot {what}.", status=400)


@bot_access_bp.route("/settings/bot-access", methods=["GET", "POST"])
@login_required
def page():
    owner = _owner_user()
    if not owner:
        abort(403)
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "issue":
            _saved, raw, err = store.issue_key(request.form.get("name") or "", owner.get("id"))
            if err:
                flash(err, "error")
            elif raw:
                session["bot_issued_key"] = raw
                flash("Key issued. Copy it now. Every switch starts off.", "success")
        elif action == "save":
            members = {int(row["id"]) for row in store.list_members()}
            try:
                key_id = int(request.form.get("key_id") or 0)
            except (TypeError, ValueError):
                key_id = 0
            controls = {
                row["id"]: request.form.get(f"switch_{row['id']}") == "1"
                for row in policy.SWITCHES
            }
            user_ids = []
            for value in request.form.getlist("voice_user"):
                try:
                    uid = int(value)
                except (TypeError, ValueError):
                    continue
                if uid in members and uid not in user_ids:
                    user_ids.append(uid)
            church_author = None
            try:
                picked = int(request.form.get("church_author") or 0)
            except (TypeError, ValueError):
                picked = 0
            if picked in members:
                church_author = picked
            ok, note = store.save_key(
                key_id,
                request.form.get("active") == "1",
                controls,
                church_author,
                user_ids,
                request.form.get("voice_church") == "1",
            )
            if not ok:
                flash(note or "Could not save that bot.", "error")
            else:
                flash(note or "Bot access saved.", "success" if not note else "error")
        elif action == "reverse":
            try:
                log_id = int(request.form.get("log_id") or 0)
            except (TypeError, ValueError):
                log_id = 0
            entry = store.get_log(log_id) if log_id else None
            if not entry:
                flash("That log entry is gone.", "error")
            else:
                ok, message = _apply_reverse(entry, f"owner:{owner.get('id')}")
                flash(message, "success" if ok else "error")
        return redirect(url_for("bot_access.page"))
    issued = session.pop("bot_issued_key", None)
    return render_template(
        "settings/bot_access.html",
        keys=store.list_keys(),
        members=store.list_members(),
        groups=policy.switch_groups(),
        issued_key=issued,
        closed=policy.CLOSED,
    )


@bot_access_bp.route("/api/bot/help", methods=["GET"])
@bot_access_bp.route("/api/bot/helper", methods=["GET"])
def api_help():
    row, err = _require_key()
    if err:
        return err
    return _json(True, policy.help_payload(row.get("controls"), row.get("voices")))


@bot_access_bp.route("/api/bot/whoami", methods=["GET"])
@bot_access_bp.route("/api/bot/me", methods=["GET"])
def api_whoami():
    row, err = _require_key()
    if err:
        return err
    return _json(True, {
        "name": row.get("name"),
        "prefix": row.get("key_prefix"),
        "active": True,
        "switches": row.get("controls") or policy.default_controls(),
        "voices": policy.help_payload(row.get("controls"), row.get("voices"))["voices"],
        "help": "GET /api/bot/help",
    })


@bot_access_bp.route("/api/bot/log", methods=["GET"])
def api_log():
    row, err = _require_key()
    if err:
        return err
    rows = store.list_log(int(row["id"]))
    return _json(True, {"entries": rows, "count": len(rows)})


@bot_access_bp.route("/api/bot/reverse", methods=["POST"])
def api_reverse():
    row, err = _require_key()
    if err:
        return err
    payload = _payload()
    try:
        log_id = int(payload.get("log_id") or 0)
    except (TypeError, ValueError):
        log_id = 0
    entry = store.get_log(log_id) if log_id else None
    if not entry or int(entry.get("key_id") or 0) != int(row["id"]):
        return _json(False, error="That log entry is not on this key.", status=404)
    step = policy.undo_plan(entry.get("action") or "", bool(entry.get("reversed")))
    ok, message = _apply_reverse(entry, f"key:{row['id']}")
    if not ok:
        return _json(False, error=message, status=400)
    words = {"hide": "hidden", "show": "restored", "restore": "restored", "reapply": "redone"}
    return _json(True, {"log_id": log_id, "result": words.get(step, step), "message": message})


@bot_access_bp.route("/api/bot/posts", methods=["GET", "POST"])
def api_posts():
    row, err = _require_key()
    if err:
        return err
    denied = _need(row, "posts")
    if denied:
        return denied
    payload = _payload()
    token = payload.get("as") or request.args.get("as") or ""
    voice, voice_err = policy.resolve_voice(token, row.get("voices") or [])
    if voice_err:
        return _json(False, error=voice_err, status=403)
    if request.method == "GET":
        posts = store.list_voice_posts(voice)
        return _json(True, {"as": voice["as"], "posts": posts, "count": len(posts)})
    post, post_err = policy.validate_post(
        payload.get("kind") or "post",
        payload.get("title") or "",
        payload.get("body") or "",
        payload.get("visibility") or "public",
    )
    if post_err:
        return _json(False, error=post_err, status=400)
    post_id, save_err = store.publish_post(voice, post)
    if not post_id:
        store.write_log(
            int(row["id"]), "post.create", ok=False, detail=save_err or "Could not save that post.",
            target_type="community_post",
        )
        return _json(False, error=save_err or "Could not save that post.", status=400)
    snapshot = {
        "post_id": post_id,
        "as": voice["as"],
        "posted_as": voice["posted_as"],
        "author_user_id": voice["user_id"],
        "kind": post["kind"],
        "title": post["title"],
        "body": post["body"],
        "visibility": post["visibility"],
    }
    log_id = store.write_log(
        int(row["id"]),
        "post.create",
        ok=True,
        detail=f"{post['kind']} as {voice['as']}: {post['title']}",
        target_type="community_post",
        target_id=post_id,
        snapshot=snapshot,
    )
    data = {
        "post_id": post_id,
        "log_id": log_id,
        "as": voice["as"],
        "kind": post["kind"],
        "title": post["title"],
        "author_user_id": voice["user_id"],
        "undo": "POST /api/bot/reverse with this log_id hides the post. The row is kept.",
    }
    if save_err:
        data["note"] = save_err
    return _json(True, data)


@bot_access_bp.route("/api/bot/security", methods=["GET"])
def api_security():
    row, err = _require_key()
    if err:
        return err
    denied = _need(row, "security")
    if denied:
        return denied
    return _json(True, _security_payload())


@bot_access_bp.route("/api/bot/read/<area>", methods=["GET"])
def api_read(area: str):
    row, err = _require_key()
    if err:
        return err
    if area not in policy.READS:
        return _json(False, error="That read is not on the bot. GET /api/bot/help lists the ones that are.", status=404)
    denied = _need(row, area)
    if denied:
        return denied
    try:
        limit = int(request.args.get("limit") or store.READ_LIMIT)
    except (TypeError, ValueError):
        limit = store.READ_LIMIT
    rows, recording, note = store.read_area(area, limit)
    data = {"area": area, "rows": rows, "count": len(rows), "recording": recording}
    if note:
        data["note"] = note
    return _json(True, data)


@bot_access_bp.route("/api/bot/sermons", methods=["GET", "POST"])
def api_sermons():
    row, err = _desk()
    if err:
        return err
    if request.method == "GET":
        if request.args.get("id"):
            try:
                sermon_id = int(request.args.get("id"))
            except (TypeError, ValueError):
                return _json(False, error="Sermon id must be a number.", status=400)
            return _finish(row, sermons.sermon_detail(sermon_id))
        return _finish(row, sermons.list_builder_sermons(request.args.get("q") or "", request.args.get("limit")))
    actor, missing = _needs_owner(row, "save a sermon")
    if missing:
        return missing
    return _finish(row, sermons.create_builder_sermon(actor, _payload()))


@bot_access_bp.route("/api/bot/sermons/<int:sermon_id>", methods=["GET", "POST"])
def api_sermon(sermon_id: int):
    row, err = _desk()
    if err:
        return err
    if request.method == "GET":
        return _finish(row, sermons.sermon_detail(sermon_id))
    return _finish(row, sermons.update_builder_sermon(sermon_id, _payload()))


@bot_access_bp.route("/api/bot/sermons/<int:sermon_id>/sections", methods=["POST"])
def api_sermon_sections(sermon_id: int):
    row, err = _desk()
    if err:
        return err
    return _finish(row, sermons.save_section(sermon_id, _payload()))


@bot_access_bp.route("/api/bot/illustrations", methods=["GET", "POST"])
def api_illustrations():
    row, err = _desk()
    if err:
        return err
    if request.method == "GET":
        return _finish(row, sermons.list_illustrations(
            request.args.get("q") or "", request.args.get("limit"), request.args.get("id"),
        ))
    actor, missing = _needs_owner(row, "save an illustration")
    if missing:
        return missing
    return _finish(row, sermons.create_illustration_item(actor, _payload()))


@bot_access_bp.route("/api/bot/illustrations/<int:illus_id>", methods=["POST"])
def api_illustration(illus_id: int):
    row, err = _desk()
    if err:
        return err
    return _finish(row, sermons.update_illustration_item(_actor_id(row), illus_id, _payload()))


@bot_access_bp.route("/api/bot/vault", methods=["GET", "POST"])
def api_vault():
    row, err = _desk()
    if err:
        return err
    if request.method == "GET":
        return _finish(row, sermons.list_vault(
            _actor_id(row), request.args.get("q") or "", request.args.get("limit"), request.args.get("id"),
        ))
    actor, missing = _needs_owner(row, "save a research note")
    if missing:
        return missing
    return _finish(row, sermons.create_vault_item(actor, _payload()))


@bot_access_bp.route("/api/bot/vault/<int:item_id>", methods=["POST"])
def api_vault_item(item_id: int):
    row, err = _desk()
    if err:
        return err
    return _finish(row, sermons.update_vault_item(_actor_id(row), item_id, _payload()))


@bot_access_bp.route("/api/bot/verses", methods=["GET"])
def api_verses():
    row, err = _desk()
    if err:
        return err
    ref = request.args.get("ref") or request.args.get("reference") or ""
    return _finish(row, sermons.lookup_reference(ref, request.args.get("translation")))


@bot_access_bp.route("/api/bot/lineup", methods=["GET", "POST"])
def api_lineup():
    row, err = _desk()
    if err:
        return err
    if request.method == "GET":
        return _finish(row, sermons.lineup_for(request.args.get("days")))
    actor, missing = _needs_owner(row, "set the lineup")
    if missing:
        return missing
    return _finish(row, sermons.set_lineup(actor, _payload()))
