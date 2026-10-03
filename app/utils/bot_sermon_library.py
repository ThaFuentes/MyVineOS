"""Illustrations, research notes, verses, and the speaking lineup."""

from __future__ import annotations

from datetime import date, timedelta

from app.utils.bot_sermon_common import (
    SECTION_TYPES,
    SHARE_VISIBILITY,
    TEXT_CAP,
    _blank_name,
    _clip,
    _db,
    _fail,
    _int_or_none,
    _jsonish,
    _like,
    _limit,
    _ok,
    _parse_date,
    _person,
    _plain,
    _sermon_brief,
    _sermon_exists,
    _tags,
    _tags_json,
    _too_big,
    _update_fields,
    as_html,
    assignments_with_speaker,
    ensure_soft_columns,
    verse_span,
)

def _illustration_item(row: dict, preview: bool) -> dict:
    item = _plain(row, (
        "id", "title", "source", "notes", "user_id", "created_at", "content",
    ))
    item["tags"] = _tags(row.get("tags"))
    item["visibility"] = "private" if row.get("user_id") else "pastoral_group"
    item["creator_name"] = _blank_name(row.get("creator_name"))
    if preview:
        content = item.get("content") or ""
        item["content"] = content[:400]
        if len(content) > 400:
            item["content_preview"] = True
    return item


def list_illustrations(search: str, limit, illus_id=None) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "illustration.list")
    try:
        cur = _db().cursor()
        if illus_id not in (None, ""):
            try:
                wanted = int(illus_id)
            except (TypeError, ValueError):
                return _fail("Illustration id must be a number.", 400)
            cur.execute(
                """
                SELECT il.id, il.title, il.content, il.source, il.tags, il.notes,
                       il.user_id, il.created_at, u.username AS creator_name
                FROM illustration_library il
                LEFT JOIN users u ON u.id = il.user_id
                WHERE il.id=%s AND il.removed_at IS NULL
                """,
                (wanted,),
            )
            row = cur.fetchone()
            if not row:
                return _fail("That illustration is not in the library.", 404)
            return _ok(_illustration_item(row, False))
        sql = """
            SELECT il.id, il.title, il.content, il.source, il.tags, il.notes,
                   il.user_id, il.created_at, u.username AS creator_name
            FROM illustration_library il
            LEFT JOIN users u ON u.id = il.user_id
            WHERE il.removed_at IS NULL
        """
        params = []
        if (search or "").strip():
            sql += " AND (il.title LIKE %s OR il.content LIKE %s OR il.source LIKE %s OR il.tags LIKE %s)"
            like = _like(search)
            params.extend([like, like, like, like])
        sql += " ORDER BY il.created_at DESC, il.id DESC LIMIT %s"
        params.append(_limit(limit))
        cur.execute(sql, params)
        rows = [_illustration_item(row, True) for row in (cur.fetchall() or [])]
        return _ok({"illustrations": rows, "count": len(rows)})
    except Exception as exc:
        print(f"bot illustrations: {exc}")
        return _fail("The illustrations could not be read.", 500, "illustration.list")


def create_illustration_item(actor_id: int, body: dict) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "illustration.create")
    body = body or {}
    title = str(body.get("title") or "").strip()[:500]
    content = str(body.get("content") or "").strip()[:TEXT_CAP]
    if not title or not content:
        return _fail("An illustration needs a title and the story.", 400)
    visibility = str(body.get("visibility") or "pastoral_group").strip().lower()
    if visibility not in SHARE_VISIBILITY:
        return _fail("visibility must be private or pastoral_group.", 400)
    try:
        from app.models.pastoral.illustrations import create_illustration
        illus_id = create_illustration({
            "title": title,
            "content": content,
            "source": _clip(body.get("source"), 500),
            "tags": body.get("tags"),
            "notes": _clip(body.get("notes"), TEXT_CAP),
            "visibility": visibility,
        }, int(actor_id))
    except Exception as exc:
        print(f"bot illustration create: {exc}")
        return _fail("That illustration could not be saved.", 500, "illustration.create")
    if not illus_id:
        return _fail("That illustration could not be saved.", 500, "illustration.create")
    return _ok(
        {"illustration_id": int(illus_id), "title": title, "visibility": visibility},
        {
            "action": "illustration.create",
            "target_type": "illustration",
            "target_id": int(illus_id),
            "detail": title,
            "snapshot": {"illustration_id": int(illus_id)},
        },
    )


def update_illustration_item(actor_id: int | None, illus_id: int, body: dict) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "illustration.update")
    try:
        cur = _db().cursor()
        cur.execute(
            """
            SELECT id, title, content, source, tags, notes, user_id
            FROM illustration_library
            WHERE id=%s AND removed_at IS NULL
            """,
            (int(illus_id),),
        )
        row = cur.fetchone()
        if not row:
            return _fail("That illustration is not in the library.", 404)
        body = body or {}
        changes = {}
        if "title" in body:
            title = str(body.get("title") or "").strip()[:500]
            if not title:
                return _fail("An illustration needs a title.", 400)
            changes["title"] = title
        if "content" in body:
            content = str(body.get("content") or "").strip()[:TEXT_CAP]
            if not content:
                return _fail("An illustration needs the story.", 400)
            changes["content"] = content
        if "source" in body:
            changes["source"] = _clip(body.get("source"), 500)
        if "tags" in body:
            changes["tags"] = _tags_json(body.get("tags"))
        if "notes" in body:
            changes["notes"] = _clip(body.get("notes"), TEXT_CAP)
        if "visibility" in body:
            visibility = str(body.get("visibility") or "").strip().lower()
            if visibility not in SHARE_VISIBILITY:
                return _fail("visibility must be private or pastoral_group.", 400)
            if visibility == "private":
                if not actor_id:
                    return _fail("This key has no owner on it, so it cannot make a private illustration.", 400)
                changes["user_id"] = int(actor_id)
            else:
                changes["user_id"] = None
        if not changes:
            return _fail("Send a title, story, source, or tags to change.", 400)
        before = {key: _jsonish(row.get(key)) for key in changes}
        after = {key: _jsonish(value) for key, value in changes.items()}
        snapshot = {"illustration_id": int(illus_id), "before": before, "after": after}
        if _too_big(snapshot):
            return _fail("That change is too large to undo, so it was not saved.", 400)
        _update_fields("illustration_library", int(illus_id), changes, ILLUSTRATION_FIELDS)
        return _ok(
            {"illustration_id": int(illus_id), **after},
            {
                "action": "illustration.update",
                "target_type": "illustration",
                "target_id": int(illus_id),
                "detail": str(after.get("title") or row.get("title") or "Illustration")[:180],
                "snapshot": snapshot,
            },
        )
    except Exception as exc:
        print(f"bot illustration update: {exc}")
        return _fail("That illustration could not be saved.", 500, "illustration.update")


def _vault_visible_sql(actor_id):
    if actor_id:
        return "(visibility='pastoral_group' OR user_id=%s)", [int(actor_id)]
    return "visibility='pastoral_group'", []


def _vault_item(row: dict, preview: bool) -> dict:
    item = _plain(row)
    item["tags"] = _tags(row.get("tags"))
    if preview:
        content = item.get("content") or ""
        item["content"] = content[:400]
        if len(content) > 400:
            item["content_preview"] = True
    return item


def list_vault(actor_id: int | None, search: str, limit, item_id=None) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "vault.list")
    try:
        where, params = _vault_visible_sql(actor_id)
        cur = _db().cursor()
        if item_id not in (None, ""):
            try:
                wanted = int(item_id)
            except (TypeError, ValueError):
                return _fail("Vault id must be a number.", 400)
            cur.execute(
                f"""
                SELECT id, user_id, title, content, reference, notes, tags, section_type,
                       scripture_reference, source_url, visibility, created_at
                FROM pastoral_vault
                WHERE id=%s AND removed_at IS NULL AND {where}
                """,
                [wanted, *params],
            )
            row = cur.fetchone()
            if not row:
                return _fail("That research note is not in the vault.", 404)
            return _ok(_vault_item(row, False))
        sql = f"""
            SELECT id, user_id, title, content, reference, notes, tags, section_type,
                   scripture_reference, source_url, visibility, created_at
            FROM pastoral_vault
            WHERE removed_at IS NULL AND {where}
        """
        if (search or "").strip():
            sql += (
                " AND (title LIKE %s OR content LIKE %s OR scripture_reference LIKE %s"
                " OR notes LIKE %s)"
            )
            like = _like(search)
            params.extend([like, like, like, like])
        sql += " ORDER BY created_at DESC, id DESC LIMIT %s"
        params.append(_limit(limit))
        cur.execute(sql, params)
        rows = [_vault_item(row, True) for row in (cur.fetchall() or [])]
        return _ok({"notes": rows, "count": len(rows)})
    except Exception as exc:
        print(f"bot vault: {exc}")
        return _fail("The research vault could not be read.", 500, "vault.list")


def create_vault_item(actor_id: int, body: dict) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "vault.create")
    body = body or {}
    title = str(body.get("title") or "").strip()[:500]
    content = str(body.get("content") or "").strip()[:TEXT_CAP]
    if not title or not content:
        return _fail("A research note needs a title and some words.", 400)
    visibility = str(body.get("visibility") or "pastoral_group").strip().lower()
    if visibility not in SHARE_VISIBILITY:
        return _fail("visibility must be private or pastoral_group.", 400)
    section_type = str(body.get("section_type") or "point").strip().lower()
    if section_type not in SECTION_TYPES:
        return _fail(
            "section_type must be introduction, point, scripture, application, illustration, conclusion, or other.",
            400,
        )
    owner_id = int(actor_id) if visibility == "private" else None
    try:
        from app.models.pastoral.vault import add_vault_item
        item_id = add_vault_item({
            "title": title,
            "content": content,
            "reference": _clip(body.get("reference"), 500),
            "notes": _clip(body.get("notes"), TEXT_CAP),
            "tags": _tags(body.get("tags")),
            "section_type": section_type,
            "scripture_reference": _clip(body.get("scripture_reference"), 500),
            "source_url": _clip(body.get("source_url"), 500),
            "visibility": visibility,
        }, owner_id)
    except Exception as exc:
        print(f"bot vault create: {exc}")
        return _fail("That research note could not be saved.", 500, "vault.create")
    if not item_id:
        return _fail("That research note could not be saved.", 500, "vault.create")
    return _ok(
        {"vault_id": int(item_id), "title": title, "visibility": visibility},
        {
            "action": "vault.create",
            "target_type": "pastoral_vault",
            "target_id": int(item_id),
            "detail": title,
            "snapshot": {"vault_id": int(item_id)},
        },
    )


def update_vault_item(actor_id: int | None, item_id: int, body: dict) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "vault.update")
    try:
        where, params = _vault_visible_sql(actor_id)
        cur = _db().cursor()
        cur.execute(
            f"""
            SELECT id, user_id, title, content, reference, notes, tags, section_type,
                   scripture_reference, source_url, visibility
            FROM pastoral_vault
            WHERE id=%s AND removed_at IS NULL AND {where}
            """,
            [int(item_id), *params],
        )
        row = cur.fetchone()
        if not row:
            return _fail("That research note is not in the vault.", 404)
        body = body or {}
        changes = {}
        if "title" in body:
            title = str(body.get("title") or "").strip()[:500]
            if not title:
                return _fail("A research note needs a title.", 400)
            changes["title"] = title
        if "content" in body:
            content = str(body.get("content") or "").strip()[:TEXT_CAP]
            if not content:
                return _fail("A research note needs some words.", 400)
            changes["content"] = content
        for key, cap in (
            ("reference", 500),
            ("notes", TEXT_CAP),
            ("scripture_reference", 500),
            ("source_url", 500),
        ):
            if key in body:
                changes[key] = _clip(body.get(key), cap)
        if "tags" in body:
            changes["tags"] = _tags_json(body.get("tags"))
        if "section_type" in body:
            section_type = str(body.get("section_type") or "").strip().lower()
            if section_type not in SECTION_TYPES:
                return _fail(
                    "section_type must be introduction, point, scripture, application, illustration, conclusion, or other.",
                    400,
                )
            changes["section_type"] = section_type
        if "visibility" in body:
            visibility = str(body.get("visibility") or "").strip().lower()
            if visibility not in SHARE_VISIBILITY:
                return _fail("visibility must be private or pastoral_group.", 400)
            changes["visibility"] = visibility
            if visibility == "private":
                if not actor_id:
                    return _fail("This key has no owner on it, so it cannot make a private note.", 400)
                changes["user_id"] = int(actor_id)
            else:
                changes["user_id"] = None
        if not changes:
            return _fail("Send the words to change on that note.", 400)
        before = {key: _jsonish(row.get(key)) for key in changes}
        after = {key: _jsonish(value) for key, value in changes.items()}
        snapshot = {"vault_id": int(item_id), "before": before, "after": after}
        if _too_big(snapshot):
            return _fail("That change is too large to undo, so it was not saved.", 400)
        _update_fields("pastoral_vault", int(item_id), changes, VAULT_FIELDS)
        return _ok(
            {"vault_id": int(item_id), **after},
            {
                "action": "vault.update",
                "target_type": "pastoral_vault",
                "target_id": int(item_id),
                "detail": str(after.get("title") or row.get("title") or "Note")[:180],
                "snapshot": snapshot,
            },
        )
    except Exception as exc:
        print(f"bot vault update: {exc}")
        return _fail("That research note could not be saved.", 500, "vault.update")


def _load_verses(ref, translation) -> dict:
    from app.models.pastoral.bible import parse_reference
    parsed = parse_reference(str(ref or ""))
    if not parsed:
        return _fail("Send a reference like John 3:16 or Romans 8:28-30.", 400)
    span = verse_span(int(parsed["verse_start"]), int(parsed["verse_end"]))
    if not span:
        return _fail("Ask for 40 verses or fewer.", 400)
    start, end = span
    trans = str(translation or "").strip() or None
    sql = """
        SELECT translation, book, chapter, verse, text
        FROM bible_verses
        WHERE book=%s AND chapter=%s AND verse BETWEEN %s AND %s
    """
    params = [parsed["book"], int(parsed["chapter"]), start, end]
    if trans:
        sql += " AND translation=%s"
        params.append(trans)
    else:
        sql += " AND translation=(SELECT code FROM bible_translations WHERE is_default=1 LIMIT 1)"
    sql += " ORDER BY verse"
    cur = _db().cursor()
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    if not rows:
        return _fail("That verse is not in the Bible loaded on this church.", 404)
    label = f"{parsed['book']} {parsed['chapter']}:{start}"
    if end != start:
        label = f"{label}-{end}"
    verses = [
        {
            "verse": int(row["verse"]),
            "text": row.get("text") or "",
            "reference": f"{row['book']} {row['chapter']}:{row['verse']}",
        }
        for row in rows
    ]
    return _ok({
        "reference": label,
        "translation": rows[0].get("translation"),
        "book": parsed["book"],
        "chapter": int(parsed["chapter"]),
        "verses": verses,
    })


def lookup_reference(ref: str, translation: str | None = None) -> dict:
    if not str(ref or "").strip():
        return _fail("Send ref= as in John 3:16.", 400)
    try:
        return _load_verses(ref, translation)
    except Exception as exc:
        print(f"bot verses: {exc}")
        return _fail("That verse could not be read.", 500, "verses")


def _lineup_card(plan: dict) -> dict:
    from app.models.pastoral.service_plans import _extract_preacher_info
    preacher = _extract_preacher_info(plan)
    service_date = plan.get("service_date")
    day = _jsonish(service_date)
    if isinstance(day, str):
        day = day[:10]
    roles = []
    for assignment in plan.get("assignments") or []:
        name = _blank_name(assignment.get("user_full_name")) or _blank_name(assignment.get("guest_name"))
        roles.append({
            "role": assignment.get("role_name"),
            "name": name,
            "user_id": _int_or_none(assignment.get("user_id")),
        })
    return {
        "date": day,
        "title": plan.get("title") or "Service",
        "source": plan.get("source") or "override",
        "start_time": _jsonish(plan.get("start_time")),
        "preacher": {"name": preacher.get("name"), "user_id": preacher.get("user_id")},
        "sermon": _sermon_brief(plan.get("pastoral_sermon_id")),
        "roles": roles,
    }


def _copy_assignments(assignments) -> list[dict]:
    rows = []
    for raw in assignments or []:
        role = str(raw.get("role_name") or "").strip()
        if not role:
            continue
        user_id = _int_or_none(raw.get("user_id"))
        guest = str(raw.get("guest_name") or "").strip() or None
        if user_id:
            guest = None
        rows.append({"role_name": role, "user_id": user_id, "guest_name": guest})
    return rows


def _write_plan(day: str, shell: dict, side: dict, actor_id: int) -> None:
    from app.models.pastoral.service_plans import create_or_update_service_plan
    create_or_update_service_plan({
        "service_date": day,
        "title": shell.get("title"),
        "notes": shell.get("notes"),
        "pastoral_sermon_id": side.get("pastoral_sermon_id"),
        "start_time": shell.get("start_time"),
        "worship_start_time": shell.get("worship_start_time"),
        "assignments": side.get("assignments") or [],
    }, int(actor_id))


def lineup_for(days) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "lineup")
    try:
        from app.models.pastoral.service_plans import get_plan_for_date
        try:
            count = int(days if days not in (None, "") else 21)
        except (TypeError, ValueError):
            count = 21
        count = max(1, min(count, 60))
        start = date.today()
        services = []
        for offset in range(count):
            day = (start + timedelta(days=offset)).isoformat()
            plan = get_plan_for_date(day)
            if not plan:
                continue
            services.append(_lineup_card(plan))
        return _ok({"days": count, "services": services, "count": len(services)})
    except Exception as exc:
        print(f"bot lineup: {exc}")
        return _fail("The lineup could not be read.", 500, "lineup")


def set_lineup(actor_id: int, body: dict) -> dict:
    problem = ensure_soft_columns()
    if problem:
        return _fail(problem, 500, "lineup.set")
    body = body or {}
    day, derr = _parse_date(body.get("date"), required=True)
    if derr:
        return _fail(derr, 400)
    try:
        preacher_id = None
        change_speaker = False
        if "preacher_id" in body or "preacher" in body:
            token = body.get("preacher_id")
            if token in (None, "") and "preacher" in body:
                token = body.get("preacher")
            if token not in (None, ""):
                preacher_id, perr = _person(token)
                if perr:
                    return _fail(perr, 400)
                change_speaker = True
        guest = str(body.get("guest_name") or "").strip()[:191]
        if guest and not preacher_id:
            change_speaker = True
        sermon_given = "sermon_id" in body
        if not change_speaker and not sermon_given:
            return _fail("Say who is speaking or which sermon.", 400)
        from app.models.pastoral.service_plans import get_plan_for_date, get_service_plan_by_date
        existing = get_service_plan_by_date(day)
        plan = existing or get_plan_for_date(day)
        if not plan:
            return _fail("That date has no service. The weekly template decides which days meet.", 400)
        sermon_id = _int_or_none(plan.get("pastoral_sermon_id"))
        if sermon_given:
            raw_sermon = body.get("sermon_id")
            if raw_sermon in (None, "", 0, "0"):
                sermon_id = None
            else:
                try:
                    sermon_id = int(raw_sermon)
                except (TypeError, ValueError):
                    return _fail("sermon_id must be a number.", 400)
                if not _sermon_exists(sermon_id):
                    return _fail("That sermon is not in the builder.", 404)
        before_assignments = _copy_assignments(plan.get("assignments"))
        after_assignments = assignments_with_speaker(
            before_assignments, preacher_id, guest or None, change_speaker,
        )
        before = {"pastoral_sermon_id": _int_or_none(plan.get("pastoral_sermon_id")), "assignments": before_assignments}
        after = {"pastoral_sermon_id": sermon_id, "assignments": after_assignments}
        _write_plan(day, plan, after, int(actor_id))
        saved = get_service_plan_by_date(day) or get_plan_for_date(day)
        card = _lineup_card(saved) if saved else {"date": day}
        return _ok(
            card,
            {
                "action": "lineup.set",
                "target_type": "service_plan",
                "target_id": int(saved["id"]) if saved and saved.get("id") else None,
                "detail": f"{day}",
                "snapshot": {
                    "date": day,
                    "created_override": existing is None,
                    "actor_id": int(actor_id),
                    "before": before,
                    "after": after,
                },
            },
        )
    except Exception as exc:
        print(f"bot lineup set: {exc}")
        return _fail("That lineup could not be saved.", 500, "lineup.set")


def _undo_lineup(plan: str, snapshot: dict):
    day = snapshot.get("date")
    if not day:
        return False, "That lineup change has no date."
    from app.models.pastoral.service_plans import get_plan_for_date, get_service_plan_by_date
    if snapshot.get("created_override") and plan == "restore":
        # Only the dated row this bot added. The weekly template stays.
        _db().cursor().execute("DELETE FROM service_plans WHERE service_date=%s", (day,))
        return True, "Removed that one-day lineup change. The weekly plan is back."
    side = snapshot.get("before") if plan == "restore" else snapshot.get("after")
    if not isinstance(side, dict):
        return False, "That lineup change has nothing to restore."
    current = get_service_plan_by_date(day) or get_plan_for_date(day)
    if not current:
        return False, "That date has no service to put the speaker back on."
    actor = _int_or_none(snapshot.get("actor_id")) or _int_or_none(current.get("created_by"))
    if not actor:
        return False, "That lineup change has no owner to save under."
    _write_plan(day, current, side, actor)
    if plan == "restore":
        return True, "Put the previous speaker and sermon back for that day."
    return True, "Applied that lineup change again."

