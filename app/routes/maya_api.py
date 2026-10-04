"""Maya's API for the church app: /api/bot/maya/* plus the Owner checklist page.

Sign-in is the normal bot flow (POST /api/bot/login -> /login/exchange ->
mvos_s_ session; POST /api/bot/password-reset rotates the key by email). On
top of that, every Maya route requires:

1. the session's key is the key the Owner designated as Maya, and
2. the route's switch is on right now on /settings/maya-permissions
   (read live from the database on every call).

Writes call the same query/model functions as the web pages, act as Maya's
acting account (picked by the Owner; defaults to the key's creator), and are
logged to bot_access_log (with a snapshot for undo) plus the office change
log or moderation ledger the UI uses. Removals are soft and restorable.
"""
from __future__ import annotations

import functools

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.datastructures import MultiDict

from app.routes import bot_access as ba
from app.utils import bot_policy as policy
from app.utils import bot_sermons as sermons
from app.utils import bot_store as store
from app.utils import maya_perms
from app.utils.decorators import login_required

maya_api_bp = Blueprint("maya_api", __name__)
MAYA_ROUTES: list[dict] = []
PREFIX = "/api/bot/maya"


# ------------------------------------------------------------------ gate


def _deny(row, code: str, message: str, perm: str | None = None):
    store.write_log(int(row["id"]), "maya.denied", ok=False, detail=f"{code}:{perm or ''}", target_type="maya")
    body = {"code": code}
    if perm:
        body["permission"] = perm
    return ba._json(False, data=body, error=message, status=403)


def need(perm: str):
    row = g.maya_row
    if perm in maya_perms.FORBIDDEN_IDS or perm not in maya_perms.CATALOG_BY_ID:
        return _deny(row, "hard_limit", "That is never available to Maya.", perm)
    if not maya_perms.allowed(row, perm):
        label = maya_perms.CATALOG_BY_ID[perm]["label"]
        return _deny(row, "permission_off", f"The Owner has '{label}' turned off for Maya.", perm)
    return None


def maya_route(rule: str, methods=("GET",), perm: str | None = None, what: str = ""):
    methods = tuple(m.upper() for m in methods)
    for m in methods:
        MAYA_ROUTES.append({"method": m, "path": PREFIX + rule, "perm": perm, "what": what})

    def deco(fn):
        @functools.wraps(fn)
        def view(*args, **kwargs):
            row, err = ba._require_key()
            if err:
                return err
            g.maya_row = row
            try:
                if not maya_perms.is_maya(row):
                    return _deny(row, "not_maya", "This key is not Maya. The Owner picks Maya on Maya permissions.")
            except Exception as exc:
                print(f"maya gate: {exc}")
                return ba._json(False, error="Maya permissions are not set up yet.", status=503)
            if perm:
                blocked = need(perm)
                if blocked:
                    return blocked
            g.maya_actor = maya_perms.acting_user_id(row)
            return fn(*args, **kwargs)

        maya_api_bp.add_url_rule(PREFIX + rule, endpoint="maya_" + fn.__name__, view_func=view, methods=list(methods))
        return fn

    return deco


def actor():
    uid = getattr(g, "maya_actor", None)
    if not uid:
        resp, status = ba._json(False, error="Maya has no acting account. The Owner sets one on Maya permissions.",
                                status=400)
        resp.status_code = status
        abort(resp)
    return int(uid)


def wrote(action: str, detail: str, *, target_type=None, target_id=None, snapshot=None, office=True) -> int | None:
    """bot_access_log row (undo trail) + office change log as Maya's acting account."""
    log_id = store.write_log(int(g.maya_row["id"]), action[:40], ok=True, detail=detail[:500],
                             target_type=target_type, target_id=target_id, snapshot=snapshot)
    if office:
        try:
            from app.models.log import log_change

            log_change(actor(), f"maya_{action}"[:60], target_id=target_id, change_details=f"[Maya] {detail}"[:500])
        except Exception as exc:
            print(f"maya log_change: {exc}")
    return log_id


def payload() -> dict:
    data = ba._payload()
    return dict(data) if not isinstance(data, dict) else data


def ok(data=None, status=200):
    return ba._json(True, data if data is not None else {}, status=status)


def bad(message, status=400):
    return ba._json(False, error=message, status=status)


def _cur():
    from app.models import moderation as mod
    from app.models.db import get_db

    mod.ensure_tables()  # adds moderation_hidden / removed columns the lists read
    return get_db().cursor()


def _limit(default=50, ceiling=200):
    try:
        return max(1, min(int(request.args.get("limit") or default), ceiling))
    except (TypeError, ValueError):
        return default


def _clean_rows(rows):
    return [store._clean(r) for r in rows or []]


# -------------------------------------------------------------- discovery


@maya_route("/capabilities", what="Every Maya route, its switch, and whether it is on now.")
def capabilities():
    row = g.maya_row
    caps = maya_perms.capabilities(row)
    state = {p["id"]: p["on"] for grp in caps["groups"] for p in grp["permissions"]}
    return ok({
        "maya": {"key": row.get("name"), "prefix": row.get("key_prefix"), "acting_user_id": g.maya_actor},
        "permissions": caps["groups"],
        "on": caps["on"],
        "hard_limits": caps["hard_limits"],
        "routes": [dict(r, allowed=(r["perm"] is None or bool(state.get(r["perm"])))) for r in MAYA_ROUTES],
        "checklist": "Read-only here. Only the Owner changes it at /settings/maya-permissions.",
        "auth": {"login": "POST /api/bot/login", "exchange": "POST /api/bot/login/exchange",
                 "reset_key": "POST /api/bot/password-reset"},
    })


# ---------------------------------------------------------- announcements


@maya_route("/announcements", perm="announcements.read", what="All announcements (active and inactive).")
def announcements_list():
    cur = _cur()
    cur.execute("SELECT id, title, content, visibility, is_active, comments_enabled, created_at, "
                "COALESCE(moderation_hidden,0) AS hidden FROM announcements ORDER BY id DESC LIMIT %s", (_limit(),))
    return ok({"announcements": _clean_rows(cur.fetchall())})


@maya_route("/announcements/<int:ann_id>", perm="announcements.read", what="One announcement with comments.")
def announcements_get(ann_id):
    from app.routes.announcements.queries import get_announcement_by_id, get_announcement_comments

    row = get_announcement_by_id(ann_id)
    if not row:
        return bad("Not found.", 404)
    return ok({"announcement": store._clean(row), "comments": _clean_rows(get_announcement_comments(ann_id))})


def _ann_fields(data, old=None):
    old = old or {}

    def flag(key, default):
        if key not in data:
            return int(old.get(key, default) or 0)
        return 1 if str(data.get(key)).lower() in ("1", "true", "yes", "on") else 0

    title = (data.get("title") if "title" in data else old.get("title")) or ""
    content = (data.get("content") if "content" in data else old.get("content")) or ""
    vis = (data.get("visibility") if "visibility" in data else old.get("visibility")) or "public"
    return title.strip(), content, vis, flag("is_active", 1), flag("comments_enabled", 1)


@maya_route("/announcements", methods=("POST",), perm="announcements.create",
            what="{title, content, visibility, is_active, comments_enabled}. is_active=1 also needs announcements.publish.")
def announcements_create():
    from app.routes.announcements.queries import create_announcement
    from app.utils.helpers import contains_censored_word

    data = payload()
    title, content, vis, active, comments = _ann_fields(data)
    if not title or not content:
        return bad("title and content are required.")
    if contains_censored_word(title) or contains_censored_word(content):
        return bad("That contains prohibited content.")
    if active and not maya_perms.allowed(g.maya_row, "announcements.publish"):
        active = 0
    new_id = create_announcement(title, content, vis, active, comments, actor())
    log_id = wrote("announcement.create", f"Announcement: {title}", target_type="announcement", target_id=new_id,
                   snapshot={"id": new_id})
    return ok({"id": new_id, "is_active": active, "log_id": log_id}, 201)


@maya_route("/announcements/<int:ann_id>", methods=("PATCH",), perm="announcements.edit",
            what="Edit; only keys you send change. Changing is_active needs announcements.publish.")
def announcements_edit(ann_id):
    from app.routes.announcements.queries import get_announcement_by_id, update_announcement
    from app.utils.helpers import contains_censored_word

    old = get_announcement_by_id(ann_id)
    if not old:
        return bad("Not found.", 404)
    data = payload()
    if "is_active" in data:
        blocked = need("announcements.publish")
        if blocked:
            return blocked
    title, content, vis, active, comments = _ann_fields(data, old)
    if contains_censored_word(title) or contains_censored_word(content):
        return bad("That contains prohibited content.")
    update_announcement(ann_id, title, content, vis, active, comments, actor())
    log_id = wrote("announcement.edit", f"Edited announcement {ann_id}", target_type="announcement",
                   target_id=ann_id, snapshot={"before": store._clean(old)})
    return ok({"id": ann_id, "log_id": log_id})


@maya_route("/announcements/<int:ann_id>/publish", methods=("POST",), perm="announcements.publish",
            what="{active: true|false}.")
def announcements_publish(ann_id):
    from app.routes.announcements.queries import get_announcement_by_id, update_announcement

    old = get_announcement_by_id(ann_id)
    if not old:
        return bad("Not found.", 404)
    active = 1 if str(payload().get("active", "1")).lower() in ("1", "true", "yes", "on") else 0
    update_announcement(ann_id, old["title"], old["content"], old["visibility"], active,
                        old.get("comments_enabled", 1), actor())
    log_id = wrote("announcement.publish", f"Announcement {ann_id} active={active}", target_type="announcement",
                   target_id=ann_id, snapshot={"before": {"is_active": old.get("is_active")}})
    return ok({"id": ann_id, "is_active": active, "log_id": log_id})


@maya_route("/announcements/<int:ann_id>/comments", methods=("POST",), perm="announcements.comment",
            what="{comment}.")
def announcements_comment(ann_id):
    from app.routes.announcements.queries import add_announcement_comment, get_announcement_by_id
    from app.utils.helpers import contains_censored_word

    if not get_announcement_by_id(ann_id):
        return bad("Not found.", 404)
    text = (payload().get("comment") or "").strip()
    if not text or contains_censored_word(text):
        return bad("comment is required and must be clean.")
    add_announcement_comment(ann_id, actor(), text)
    log_id = wrote("announcement.comment", f"Comment on announcement {ann_id}", target_type="announcement",
                   target_id=ann_id)
    return ok({"log_id": log_id}, 201)


# ------------------------------------------- shared hide/restore (soft delete)

KIND_PERM = {"announcement": "announcements", "prayer": "prayers", "event": "events", "dream": "dreams",
             "prophecy": "prophecies", "sermon": "sermons", "post": "wall"}


def _soft_delete(kind: str, item_id: int):
    from app.models import moderation as mod

    reason = (payload().get("reason") or "Removed by Maya")[:200]
    ok_, msg = mod.soft_delete_content(kind, int(item_id), actor(), reason)
    if not ok_:
        return bad(msg, 409)
    log_id = wrote(f"{kind}.delete", f"Removed {kind} {item_id}: {reason}", target_type=kind, target_id=item_id,
                   snapshot={"kind": kind, "id": item_id}, office=False)
    return ok({"removed": True, "message": msg, "log_id": log_id,
               "restore": f"POST {PREFIX}/{kind}s/{item_id}/restore".replace("prophecys", "prophecies")})


def _restore(kind: str, item_id: int):
    from app.models import moderation as mod

    ok_, msg = mod.restore_target(kind, int(item_id), actor(), "Restored by Maya")
    if not ok_:
        return bad(msg, 409)
    log_id = wrote(f"{kind}.restore", f"Restored {kind} {item_id}", target_type=kind, target_id=item_id, office=False)
    return ok({"restored": True, "message": msg, "log_id": log_id})


def _register_soft(kind: str, plural: str):
    area = KIND_PERM[kind]

    def delete_view(item_id):
        return _soft_delete(kind, item_id)

    def restore_view(item_id):
        return _restore(kind, item_id)

    delete_view.__name__ = f"{plural}_delete"
    restore_view.__name__ = f"{plural}_restore"
    maya_route(f"/{plural}/<int:item_id>", methods=("DELETE",), perm=f"{area}.delete",
               what=f"Soft-delete (hidden, row kept, ledger entry). Body {{reason}}.")(delete_view)
    maya_route(f"/{plural}/<int:item_id>/restore", methods=("POST",), perm=f"{area}.restore",
               what="Put it back.")(restore_view)


for _kind, _plural in (("announcement", "announcements"), ("prayer", "prayers"), ("event", "events"),
                       ("dream", "dreams"), ("prophecy", "prophecies"), ("sermon", "sermons"), ("post", "posts")):
    _register_soft(_kind, _plural)


@maya_route("/announcements/<int:ann_id>/destroy", methods=("POST",), perm="hard_delete",
            what="HIGH RISK. Permanently delete. Body {confirm: 'DELETE'}. Snapshot kept in Maya's log.")
def announcements_destroy(ann_id):
    from app.routes.announcements.queries import delete_announcement, get_announcement_by_id, get_announcement_comments

    if str(payload().get("confirm") or "") != "DELETE":
        return bad("Send {\"confirm\": \"DELETE\"} to permanently delete.")
    old = get_announcement_by_id(ann_id)
    if not old:
        return bad("Not found.", 404)
    snap = {"announcement": store._clean(old), "comments": _clean_rows(get_announcement_comments(ann_id))}
    title = delete_announcement(ann_id)
    log_id = wrote("announcement.destroy", f"PERMANENTLY deleted announcement: {title}", target_type="announcement",
                   target_id=ann_id, snapshot=snap)
    return ok({"destroyed": True, "log_id": log_id, "note": "Cannot be undone. The full text is in Maya's log."})


# ---------------------------------------------------------------- prayers


@maya_route("/prayers", perm="prayers.read", what="Prayer requests incl. pending/held. ?status=")
def prayers_list():
    status = (request.args.get("status") or "").strip().lower()
    cur = _cur()
    sql = ("SELECT id, title, description, visibility, status, user_id, contributor_name, date_posted, "
           "COALESCE(moderation_hidden,0) AS hidden FROM prayers")
    args = []
    if status:
        sql += " WHERE status=%s"
        args.append(status)
    cur.execute(sql + " ORDER BY id DESC LIMIT %s", (*args, _limit()))
    return ok({"prayers": _clean_rows(cur.fetchall())})


@maya_route("/prayers/<int:prayer_id>", perm="prayers.read", what="One prayer with responses.")
def prayers_get(prayer_id):
    from app.routes.prayers.queries import get_prayer_by_id, get_prayer_responses

    row = get_prayer_by_id(prayer_id, True, actor())
    if not row:
        return bad("Not found.", 404)
    return ok({"prayer": store._clean(row), "responses": _clean_rows(get_prayer_responses(prayer_id))})


@maya_route("/prayers", methods=("POST",), perm="prayers.create", what="{title, description, visibility}.")
def prayers_create():
    from app.routes.prayers.queries import create_prayer
    from app.utils.helpers import contains_censored_word

    data = payload()
    title, desc = (data.get("title") or "").strip(), (data.get("description") or "").strip()
    if not title or not desc:
        return bad("title and description are required.")
    if contains_censored_word(title) or contains_censored_word(desc):
        return bad("That contains prohibited content.")
    new_id = create_prayer(title, desc, data.get("visibility") or "private", actor(), "", "", status="approved")
    log_id = wrote("prayer.create", f"Prayer: {title}", target_type="prayer", target_id=new_id)
    return ok({"id": new_id, "log_id": log_id}, 201)


@maya_route("/prayers/<int:prayer_id>", methods=("PATCH",), perm="prayers.edit", what="{title, description, visibility}.")
def prayers_edit(prayer_id):
    from app.routes.prayers.queries import get_prayer_by_id, update_prayer

    old = get_prayer_by_id(prayer_id, True, actor())
    if not old:
        return bad("Not found.", 404)
    data = payload()
    update_prayer(prayer_id, data.get("title", old["title"]), data.get("description", old["description"]),
                  data.get("visibility", old["visibility"]))
    log_id = wrote("prayer.edit", f"Edited prayer {prayer_id}", target_type="prayer", target_id=prayer_id,
                   snapshot={"before": store._clean(old)})
    return ok({"id": prayer_id, "log_id": log_id})


@maya_route("/prayers/<int:prayer_id>/status", methods=("POST",), perm="prayers.approve",
            what="{status: approved|pending|rejected}.")
def prayers_status(prayer_id):
    from app.routes.prayers.queries import get_prayer_by_id, update_prayer_status

    status = (payload().get("status") or "").strip().lower()
    if status not in ("approved", "pending", "rejected"):
        return bad("status must be approved, pending or rejected.")
    old = get_prayer_by_id(prayer_id, True, actor())
    if not old:
        return bad("Not found.", 404)
    update_prayer_status(prayer_id, status)
    log_id = wrote("prayer.status", f"Prayer {prayer_id} -> {status}", target_type="prayer", target_id=prayer_id,
                   snapshot={"before": {"status": old.get("status")}})
    return ok({"id": prayer_id, "status": status, "log_id": log_id})


# ----------------------------------------------------------------- events


@maya_route("/events", perm="events.read", what="Events.")
def events_list():
    cur = _cur()
    cur.execute("SELECT id, event_name, event_date, event_time, location, visibility, "
                "LEFT(description, 500) AS description, COALESCE(moderation_hidden,0) AS hidden "
                "FROM events ORDER BY event_date DESC LIMIT %s", (_limit(),))
    return ok({"events": _clean_rows(cur.fetchall())})


@maya_route("/events/<int:event_id>", perm="events.read", what="One event (all fields).")
def events_get(event_id):
    from app.services.church_events import get_event

    row = get_event(event_id)
    return ok({"event": store._clean(row)}) if row else bad("Not found.", 404)


def _form(data: dict, base=None) -> MultiDict:
    out = MultiDict(base or {})
    for key, val in data.items():
        if key == "payment_option_ids":
            out.poplist(key)
            for part in (val if isinstance(val, list) else str(val).split(",")):
                out.add(key, str(part).strip())
        elif key in ("potluck_enabled", "payment_required"):
            out.poplist(key)
            if str(val).lower() in ("1", "true", "yes", "on"):
                out[key] = "1"
        else:
            out[key] = "" if val is None else str(val)
    return out


@maya_route("/events", methods=("POST",), perm="events.create",
            what="Same fields as the Add event form (event_name, event_date, event_time, location, description, visibility, ...). visibility=public needs events.publish.")
def events_create():
    from app.services.church_events import create_event

    data = payload()
    if (data.get("visibility") or "private") != "private" and not maya_perms.allowed(g.maya_row, "events.publish"):
        data["visibility"] = "private"
    new_id, err = create_event(_form(data), actor())
    if err:
        return bad(err)
    log_id = wrote("event.create", f"Event: {data.get('event_name')}", target_type="event", target_id=new_id,
                   office=False)
    return ok({"id": new_id, "visibility": data.get("visibility") or "private", "log_id": log_id}, 201)


@maya_route("/events/<int:event_id>", methods=("PATCH",), perm="events.edit",
            what="Partial edit; unsent fields keep their value. Changing visibility needs events.publish.")
def events_edit(event_id):
    from app.services.church_events import get_event, row_as_form, update_event

    data = payload()
    if "visibility" in data:
        blocked = need("events.publish")
        if blocked:
            return blocked
    old = get_event(event_id)
    if not old:
        return bad("Not found.", 404)
    ok_, err, before = update_event(event_id, _form(data, row_as_form(old)), actor())
    if not ok_:
        return bad(err)
    log_id = wrote("event.edit", f"Edited event {event_id}", target_type="event", target_id=event_id,
                   snapshot={"before": store._clean(before)}, office=False)
    return ok({"id": event_id, "log_id": log_id})


@maya_route("/events/<int:event_id>/destroy", methods=("POST",), perm="hard_delete",
            what="HIGH RISK. Permanently delete an event and its potluck signups. Body {confirm: 'DELETE'}.")
def events_destroy(event_id):
    from app.services.church_events import get_event, hard_delete_event

    if str(payload().get("confirm") or "") != "DELETE":
        return bad("Send {\"confirm\": \"DELETE\"} to permanently delete.")
    old = get_event(event_id)
    if not old:
        return bad("Not found.", 404)
    ok_, msg = hard_delete_event(event_id, actor())
    if not ok_:
        return bad(msg, 409)
    log_id = wrote("event.destroy", msg, target_type="event", target_id=event_id,
                   snapshot={"event": store._clean(old)}, office=False)
    return ok({"destroyed": True, "log_id": log_id})


# ------------------------------------------------------------- wall posts


@maya_route("/posts", perm="wall.read", what="Recent wall posts (incl. removed flag).")
def posts_list():
    cur = _cur()
    cur.execute("SELECT id, user_id, kind, title, LEFT(body, 500) AS body, visibility, created_at, "
                "removed_at, (removed_at IS NOT NULL) AS hidden FROM community_posts "
                "ORDER BY id DESC LIMIT %s", (_limit(),))
    return ok({"posts": _clean_rows(cur.fetchall())})


@maya_route("/posts", methods=("POST",), perm="wall.create",
            what="{as: church|user:ID, kind, title, body, visibility}. Voices are attached by the Owner on Bot access.")
def posts_create():
    data = payload()
    voice, verr = policy.resolve_voice(data.get("as") or "", g.maya_row.get("voices") or [])
    if verr:
        return bad(verr, 403)
    post, perr = policy.validate_post(data.get("kind") or "post", data.get("title") or "", data.get("body") or "",
                                      data.get("visibility") or "public")
    if perr:
        return bad(perr)
    post_id, err = store.publish_post(voice, post)
    if not post_id:
        return bad(err or "Could not save that post.")
    log_id = wrote("post.create", f"{post['kind']} as {voice['as']}: {post['title']}", target_type="community_post",
                   target_id=post_id, snapshot={"post_id": post_id, "as": voice["as"]}, office=False)
    return ok({"post_id": post_id, "log_id": log_id, "note": err}, 201)


# --------------------------------------------------------------- comments


@maya_route("/comments/<table>/<int:comment_id>", perm="comments.read", what="One comment. table = event_comments, sermon_comments, ...")
def comments_get(table, comment_id):
    from app.models import moderation as mod

    row = mod.get_comment(table, comment_id)
    return ok({"comment": store._clean(row)}) if row else bad("Not found.", 404)


@maya_route("/comments/<table>/<int:comment_id>", methods=("DELETE",), perm="comments.delete",
            what="Soft-remove a comment (ledger entry, restorable).")
def comments_delete(table, comment_id):
    from app.models import moderation as mod

    if not mod.comment_table_ok(table):
        return bad("Unknown comment table.", 404)
    if not mod.soft_delete_comment(table, comment_id, actor(), (payload().get("reason") or "Removed by Maya")[:200]):
        return bad("Could not remove that comment.", 409)
    log_id = wrote("comment.delete", f"Removed {table} {comment_id}", target_type=table, target_id=comment_id,
                   office=False)
    return ok({"removed": True, "log_id": log_id})


@maya_route("/comments/<table>/<int:comment_id>/restore", methods=("POST",), perm="comments.restore", what="Put a comment back.")
def comments_restore(table, comment_id):
    from app.models import moderation as mod

    ok_, msg = mod.restore_comment(table, comment_id, actor(), "Restored by Maya")
    if not ok_:
        return bad(msg, 409)
    log_id = wrote("comment.restore", f"Restored {table} {comment_id}", target_type=table, target_id=comment_id,
                   office=False)
    return ok({"restored": True, "message": msg, "log_id": log_id})


# -------------------------------------------------------- moderation desk


@maya_route("/moderation/removed", perm="moderation.read", what="Hidden / soft-deleted items that can be restored.")
def moderation_removed():
    from app.models import moderation as mod

    return ok({"removed": _clean_rows(mod.list_removed(_limit(60, 200)))})


@maya_route("/moderation/actions", perm="moderation.read", what="Moderation ledger. ?status=active|reversed|upheld")
def moderation_actions():
    from app.models import moderation as mod

    return ok({"actions": _clean_rows(mod.list_actions(status=request.args.get("status") or "active",
                                                       limit=_limit(80, 200)))})


@maya_route("/moderation/restore", methods=("POST",), perm="moderation.restore",
            what="{kind, id, table (comments only)} — the desk's Restore button.")
def moderation_restore():
    from app.models import moderation as mod

    data = payload()
    try:
        item_id = int(data.get("id") or 0)
    except (TypeError, ValueError):
        item_id = 0
    if not item_id or not data.get("kind"):
        return bad("kind and id are required.")
    ok_, msg = mod.restore_target(str(data["kind"]), item_id, actor(), "Restored by Maya", table=data.get("table"))
    if not ok_:
        return bad(msg, 409)
    log_id = wrote("moderation.restore", f"Restored {data['kind']} {item_id}", target_type=str(data["kind"]),
                   target_id=item_id, office=False)
    return ok({"restored": True, "message": msg, "log_id": log_id})


@maya_route("/moderation/actions/<int:action_id>/<verb>", methods=("POST",), perm="moderation.review",
            what="verb = reverse | uphold.")
def moderation_review(action_id, verb):
    from app.models import moderation as mod

    act = mod.get_action(action_id)
    if not act:
        return bad("Not found.", 404)
    if verb == "reverse":
        msg = mod.reverse_action(action_id, actor(), "Reversed by Maya")
    elif verb == "uphold":
        msg = mod.uphold_action(action_id, actor())
    else:
        return bad("verb must be reverse or uphold.", 404)
    log_id = wrote(f"moderation.{verb}", f"{verb} action {action_id}", target_type="moderation_action",
                   target_id=action_id, office=False)
    return ok({"message": msg, "log_id": log_id})


# ------------------------------------------------------------ church page


@maya_route("/church-page", perm="church_page.read", what="The church page (about, verse, colors).")
def church_page_get():
    from app.models.church_community import get_canonical_church_page

    return ok({"page": store._clean(get_canonical_church_page(0))})


@maya_route("/church-page", methods=("PATCH",), perm="church_page.edit", what="{about, verse}.")
def church_page_edit():
    from app.models.church_community import canonical_page_id, get_canonical_church_page, save_church_page

    old = get_canonical_church_page(0) or {}
    data = payload()
    about = data.get("about", old.get("about") or "")
    verse = data.get("verse", old.get("verse") or old.get("favorite_verse") or "")
    save_church_page(canonical_page_id(0), about, verse, actor())
    log_id = wrote("church_page.edit", "Edited the church page", target_type="church_page",
                   snapshot={"before": {"about": old.get("about"), "verse": old.get("verse")}})
    return ok({"saved": True, "log_id": log_id})


# --------------------------------------------------------- sermon builder


def _finish(result):
    return ba._finish(g.maya_row, result)


@maya_route("/builder/sermons", perm="builder.read", what="Builder sermons. ?q=&limit=")
def builder_list():
    return _finish(sermons.list_builder_sermons(request.args.get("q") or "", request.args.get("limit")))


@maya_route("/builder/sermons/<int:sermon_id>", perm="builder.read", what="One builder sermon.")
def builder_get(sermon_id):
    return _finish(sermons.sermon_detail(sermon_id))


@maya_route("/builder/sermons", methods=("POST",), perm="builder.create", what="Same body as POST /api/bot/sermons.")
def builder_create():
    return _finish(sermons.create_builder_sermon(actor(), payload()))


@maya_route("/builder/sermons/<int:sermon_id>", methods=("PATCH",), perm="builder.edit", what="Update a draft.")
def builder_edit(sermon_id):
    return _finish(sermons.update_builder_sermon(sermon_id, payload()))


@maya_route("/builder/sermons/<int:sermon_id>/sections", methods=("POST",), perm="builder.edit", what="Save a section.")
def builder_section(sermon_id):
    return _finish(sermons.save_section(sermon_id, payload()))


@maya_route("/builder/illustrations", perm="builder.read", what="Illustrations. ?q=&id=")
def illustrations_list():
    return _finish(sermons.list_illustrations(request.args.get("q") or "", request.args.get("limit"),
                                              request.args.get("id")))


@maya_route("/builder/illustrations", methods=("POST",), perm="builder.create", what="New illustration.")
def illustrations_create():
    return _finish(sermons.create_illustration_item(actor(), payload()))


@maya_route("/builder/illustrations/<int:illus_id>", methods=("PATCH",), perm="builder.edit", what="Edit illustration.")
def illustrations_edit(illus_id):
    return _finish(sermons.update_illustration_item(actor(), illus_id, payload()))


@maya_route("/builder/research", perm="builder.read", what="Research notes. ?q=&id=")
def research_list():
    return _finish(sermons.list_vault(actor(), request.args.get("q") or "", request.args.get("limit"),
                                      request.args.get("id")))


@maya_route("/builder/research", methods=("POST",), perm="builder.create", what="New research note.")
def research_create():
    return _finish(sermons.create_vault_item(actor(), payload()))


@maya_route("/builder/research/<int:item_id>", methods=("PATCH",), perm="builder.edit", what="Edit research note.")
def research_edit(item_id):
    return _finish(sermons.update_vault_item(actor(), item_id, payload()))


@maya_route("/verses", perm="verses.read", what="?ref=John 3:16&translation=")
def verses():
    return _finish(sermons.lookup_reference(request.args.get("ref") or "", request.args.get("translation")))


@maya_route("/lineup", perm="lineup.read", what="?days=")
def lineup_get():
    return _finish(sermons.lineup_for(request.args.get("days")))


@maya_route("/lineup", methods=("POST",), perm="lineup.edit", what="Same body as POST /api/bot/lineup.")
def lineup_set():
    return _finish(sermons.set_lineup(actor(), payload()))


# ------------------------------------------------------------------ reads

READ_PERMS = {"groups": "groups.read", "attendance": "attendance.read", "worship": "worship.read",
              "tickets": "tickets.read", "inventory": "inventory.read", "audit": "audit.read",
              "dreams": "dreams.read", "prophecies": "prophecies.read", "sermons": "sermons.read",
              "donations": "giving.read", "bills": "bills.read"}


@maya_route("/read/<area>", what="Read-only lists: " + ", ".join(sorted(READ_PERMS)) + ". Each has its own switch.")
def read_area(area):
    perm = READ_PERMS.get(area)
    if not perm:
        return bad("Unknown area.", 404)
    blocked = need(perm)
    if blocked:
        return blocked
    rows, recording, note = store.read_area(area, _limit(50, 100))
    store.write_log(int(g.maya_row["id"]), "maya.read", ok=True, detail=area, target_type="read")
    return ok({"area": area, "rows": rows, "count": len(rows), "recording": recording, "note": note or None})


@maya_route("/members", perm="members.read", what="Directory: id, username, name, role. Email/phone need members.contact.")
def members_list():
    contact = maya_perms.allowed(g.maya_row, "members.contact")
    cols = "id, username, first_name, last_name, role" + (", email, phone" if contact else "")
    cur = _cur()
    cur.execute(f"SELECT {cols} FROM users ORDER BY id DESC LIMIT %s", (_limit(100, 500),))
    store.write_log(int(g.maya_row["id"]), "maya.read", ok=True, detail="members", target_type="read")
    return ok({"members": _clean_rows(cur.fetchall()), "contact_included": contact})


@maya_route("/security", perm="security.read", what="Security summary and recent events.")
def security():
    return ok(ba._security_payload())


@maya_route("/notifications", perm="notifications.read", what="Maya's acting account's notifications.")
def notifications():
    from app.models.notices import list_notices

    return ok({"notices": _clean_rows(list_notices(actor(), _limit(12, 50)))})


@maya_route("/log", perm="log.read", what="Everything this key did.")
def log_list():
    rows = store.list_log(int(g.maya_row["id"]), _limit(50, 200))
    return ok({"entries": rows, "count": len(rows)})


@maya_route("/log/<int:log_id>/undo", methods=("POST",), perm="log.undo", what="Undo one of Maya's own actions.")
def log_undo(log_id):
    entry = store.get_log(log_id)
    if not entry or int(entry.get("key_id") or 0) != int(g.maya_row["id"]):
        return bad("That log entry is not on this key.", 404)
    action = entry.get("action") or ""
    kind = action.split(".")[0]
    if action.endswith(".delete") and kind in KIND_PERM:
        from app.models import moderation as mod

        ok_, msg = mod.restore_target(kind, int(entry.get("target_id") or 0), actor(), "Undo by Maya")
    elif action == "comment.delete":
        from app.models import moderation as mod

        ok_, msg = mod.restore_comment(entry.get("target_type") or "", int(entry.get("target_id") or 0), actor(),
                                       "Undo by Maya")
    else:
        ok_, msg = ba._apply_reverse(entry, f"maya:{g.maya_row['id']}")
        if ok_:
            return ok({"undone": True, "message": msg})
        return bad(msg)
    if ok_:
        store.mark_reversed(log_id, f"maya:{g.maya_row['id']}", clear=False)
        return ok({"undone": True, "message": msg})
    return bad(msg, 409)


# -------------------------------------------------------- users (high risk)


def _target_user(user_id):
    from app.models.users import get_user_by_id

    user = get_user_by_id(int(user_id))
    if not user:
        return None, bad("Not found.", 404)
    if int(user["id"]) == int(actor()):
        return None, _deny(g.maya_row, "hard_limit", "Maya cannot change her own account.")
    if (user.get("role") or "") in ("Owner", "Admin"):
        return None, _deny(g.maya_row, "hard_limit", "Maya cannot change an Owner or Admin account.")
    return user, None


@maya_route("/users/<int:user_id>/approve", methods=("POST",), perm="users.approve",
            what="HIGH RISK. {role: Member|Visitor|Staff}. Only pending signups.")
def users_approve(user_id):
    from app.models.users import approve_user

    user, err = _target_user(user_id)
    if err:
        return err
    role = (payload().get("role") or "Member").strip().title()
    if role not in ("Member", "Visitor", "Staff"):
        return bad("role must be Member, Visitor or Staff.")
    if (user.get("role") or "") != "pending":
        return bad("That account is not pending.", 409)
    approve_user(int(user_id), actor(), role)
    log_id = wrote("user.approve", f"Approved {user.get('username')} as {role}", target_type="user",
                   target_id=user_id, office=False)
    return ok({"approved": True, "role": role, "log_id": log_id})


@maya_route("/users/<int:user_id>/ban", methods=("POST",), perm="users.ban", what="HIGH RISK. {banned: true|false}.")
def users_ban(user_id):
    from app.models.users import ban_user, unban_user

    user, err = _target_user(user_id)
    if err:
        return err
    banned = str(payload().get("banned", "true")).lower() in ("1", "true", "yes", "on")
    if banned:
        ban_user(int(user_id), actor())
    else:
        unban_user(int(user_id), actor())
    log_id = wrote("user.ban" if banned else "user.unban", f"{'Banned' if banned else 'Unbanned'} {user.get('username')}",
                   target_type="user", target_id=user_id, snapshot={"previous_role": user.get("role")}, office=False)
    return ok({"banned": banned, "log_id": log_id})


# ------------------------------------------------------- Owner checklist


def _owner_or_403():
    owner = ba._owner_user()
    if not owner:
        abort(403)
    return owner


@maya_api_bp.route("/settings/maya-permissions", methods=["GET"])
@login_required
def owner_page():
    _owner_or_403()
    maya_perms.ensure_tables()
    s = maya_perms.settings_row()
    keys = store.list_keys()
    state = maya_perms.perm_state(int(s["key_id"])) if s else {}
    expiry = maya_perms.perm_expiry(int(s["key_id"])) if s else {}
    return render_template(
        "settings/maya_permissions.html",
        settings=s,
        keys=keys,
        members=store.list_members(),
        groups=maya_perms.groups(),
        state=state,
        expiry=expiry,
        remaining=maya_perms.remaining_text,
        units=list(maya_perms.EXPIRY_UNITS),
        hard_limits=maya_perms.HARD_LIMITS,
        log=maya_perms.recent_log(40),
    )


@maya_api_bp.route("/settings/maya-permissions/account", methods=["POST"])
@login_required
def owner_set_account():
    owner = _owner_or_403()
    try:
        key_id = int(request.form.get("key_id") or 0)
        acting = int(request.form.get("acting_user_id") or 0) or None
    except (TypeError, ValueError):
        key_id, acting = 0, None
    ok_, msg = maya_perms.set_maya(key_id, acting, owner_id=owner.get("id")) if key_id else (False, "Pick a key.")
    flash(msg, "success" if ok_ else "error")
    return redirect(url_for("maya_api.owner_page"))


@maya_api_bp.route("/settings/maya-permissions", methods=["POST"])
@login_required
def owner_save():
    owner = _owner_or_403()
    s = maya_perms.settings_row()
    if not s:
        flash("Pick Maya's key first.", "error")
        return redirect(url_for("maya_api.owner_page"))
    key_id = int(s["key_id"])
    on = set(request.form.getlist("perm"))
    wanted = {pid: pid in on for pid in maya_perms.CATALOG_BY_ID}
    current = maya_perms.perm_state(key_id)
    expiry, bad_timer = {}, []
    for pid in on:
        perm = maya_perms.CATALOG_BY_ID.get(pid)
        if perm is None:
            continue
        unit = (request.form.get(f"exp_unit_{pid}") or "keep").strip().lower()
        if unit == "keep":
            continue
        if unit in ("none", "") and perm["high_risk"]:
            bad_timer.append(perm["label"])
            continue
        try:
            expiry[pid] = maya_perms.parse_expiry(unit, request.form.get(f"exp_n_{pid}") or "1")
        except ValueError:
            bad_timer.append(perm["label"])
    if bad_timer:
        flash("Timer not understood for: " + ", ".join(bad_timer) + ". High-risk switches got the 24-hour default.",
              "error")
    confirmed = None
    if any(wanted[p] and not current.get(p) and maya_perms.CATALOG_BY_ID[p]["high_risk"] for p in wanted) \
            or any(maya_perms.CATALOG_BY_ID[p]["high_risk"] for p in expiry):
        confirmed = maya_perms.confirm_owner(owner, request.form.get("confirm_password") or "",
                                             request.form.get("confirm_code") or "")
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()[:64]
    changed, refused = maya_perms.save_state(key_id, wanted, owner=owner, confirmed_with=confirmed, ip=ip,
                                             expiry=expiry)
    if refused:
        flash("High-risk switches stayed OFF (enter your password or 2FA code to turn them on): "
              + ", ".join(maya_perms.CATALOG_BY_ID[p]["label"] for p in refused), "error")
    flash(f"Saved. {len(changed)} change(s), live now." if changed else "No changes.", "success")
    return redirect(url_for("maya_api.owner_page"))
