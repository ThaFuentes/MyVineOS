# Threat-map queries. Imported only from threat_map.py (page-scoped).
from __future__ import annotations

import time
from typing import Any

from . import queries as q
from .geo_lookup import ensure_ip_geo_table, fill_missing_ips
from .queries import _fmt_ts

WINDOWS = {
    "live": "15 MINUTE",
    "24h": "1 DAY",
    "7d": "7 DAY",
    "30d": "30 DAY",
}


def _window_sql(window: str) -> str:
    return WINDOWS.get((window or "24h").strip().lower(), WINDOWS["24h"])


def _skip_sql() -> tuple[str, list]:
    types = list(q._SKIP_EVENT_TYPES)
    if types:
        ph = ",".join(["%s"] * len(types))
        clause = f"(e.event_type IS NULL OR e.event_type NOT IN ({ph}))"
        params = list(types)
    else:
        clause = "1=1"
        params = []
    # Rate-limit from a signed-in account is product use, not an attack.
    clause += (
        " AND NOT (e.user_id IS NOT NULL AND e.user_id != 0"
        " AND (e.event_type LIKE %s OR e.event_type LIKE %s))"
    )
    params.extend(["%rate_limit%", "%rate_limited%"])
    return clause, params


def _family(raw: str | None) -> str:
    return q._canonical_attack_type(raw) or "other"


def _safe_username(raw: Any) -> str:
    s = "".join(ch for ch in str(raw or "") if ch.isprintable()).strip()
    return s[:40]


def _usernames_by_id(uids: set[int]) -> dict[int, str]:
    if not uids:
        return {}
    try:
        from app.models.users import get_user_by_id

        out: dict[int, str] = {}
        for uid in uids:
            u = get_user_by_id(int(uid))
            if not u:
                continue
            name = _safe_username(u.get("username") if isinstance(u, dict) else getattr(u, "username", None))
            if name:
                out[int(uid)] = name
        return out
    except Exception as exc:
        print(f"[threat-map] username lookup: {exc}")
        return {}


def _attach_usernames(rows: list[dict], *, keep_ip: bool = False) -> None:
    """Username only when the event itself has user_id.

    Do not guess from IP sightings — a shared office NAT would stamp the
    last person on that IP onto someone else's hit.
    """
    uids = set()
    for r in rows:
        try:
            uid = int(r.get("user_id") or 0)
        except (TypeError, ValueError):
            uid = 0
        r["user_id"] = uid or None
        if uid:
            uids.add(uid)
    names = _usernames_by_id(uids)
    for r in rows:
        uid = r.get("user_id")
        r["username"] = names.get(int(uid)) if uid else None
        r.pop("user_id", None)
        if not keep_ip:
            r.pop("ip", None)


def countries_for_window(window: str = "24h", *, fill: bool = True) -> dict[str, Any]:
    t0 = time.monotonic()
    win = _window_sql(window)
    skip_sql, skip_params = _skip_sql()
    conn = q._sec()
    empty = {
        "countries": [],
        "unresolved_ips": 0,
        "private_events": 0,
        "filled": 0,
        "window": window,
        "q_ms": 0,
        "geo_ready": False,
    }
    if conn is None:
        return empty
    filled = 0
    try:
        cur = conn.cursor()
        ensure_ip_geo_table(conn)
        if fill and (window or "") != "live":
            try:
                cur.execute(
                    f"""
                    SELECT DISTINCT e.ip
                    FROM pbt_security_events e
                    LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
                    WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
                      AND e.ip IS NOT NULL AND e.ip != ''
                      AND {skip_sql}
                      AND (g.ip IS NULL OR g.resolved_at < NOW() - INTERVAL 90 DAY)
                    LIMIT 200
                    """,
                    skip_params,
                )
                missing = [(r.get("ip") if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])]
                filled = fill_missing_ips(conn, missing, limit=200)
            except Exception as exc:
                print(f"[threat-map] fill missing: {exc}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        cur.execute(
            f"""
            SELECT COALESCE(g.country_iso2, 'XX') AS cc,
                   e.event_type,
                   COUNT(*) AS c,
                   COUNT(DISTINCT e.ip) AS ips,
                   MAX(COALESCE(e.created_at, e.timestamp)) AS last_seen
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
            GROUP BY cc, e.event_type
            """,
            skip_params,
        )
        rows = list(cur.fetchall() or [])
        by_cc: dict[str, dict] = {}
        private = 0
        unresolved = 0
        for r in rows:
            cc = (r.get("cc") or "XX").upper()
            fam = _family(r.get("event_type"))
            if not fam:
                continue
            cnt = int(r.get("c") or 0)
            if cc == "ZZ":
                private += cnt
            if cc == "XX":
                unresolved += int(r.get("ips") or 0)
            bucket = by_cc.setdefault(
                cc,
                {
                    "iso2": cc,
                    "count": 0,
                    "unique_ips": 0,
                    "last_seen": None,
                    "families": {},
                    "top_family": "other",
                },
            )
            bucket["count"] += cnt
            bucket["unique_ips"] += int(r.get("ips") or 0)
            bucket["families"][fam] = bucket["families"].get(fam, 0) + cnt
            last = r.get("last_seen")
            if last and (bucket["last_seen"] is None or last > bucket["last_seen"]):
                bucket["last_seen"] = last
        countries = []
        for cc, b in by_cc.items():
            if b["families"]:
                b["top_family"] = max(b["families"], key=b["families"].get)
            if b["last_seen"] is not None:
                b["last_seen"] = _fmt_ts(b["last_seen"])
            countries.append(b)
        countries.sort(key=lambda x: x["count"], reverse=True)
        empty.update(
            {
                "countries": countries,
                "unresolved_ips": unresolved,
                "private_events": private,
                "filled": filled,
                "geo_ready": True,
                "q_ms": int((time.monotonic() - t0) * 1000),
            }
        )
        return empty
    except Exception as exc:
        print(f"[threat-map] countries_for_window: {exc}")
        empty["q_ms"] = int((time.monotonic() - t0) * 1000)
        return empty
    finally:
        q._close(conn)


def summary_for_window(window: str = "24h") -> dict[str, Any]:
    t0 = time.monotonic()
    win = _window_sql(window)
    skip_sql, skip_params = _skip_sql()
    conn = q._sec()
    out = {
        "window": window,
        "total": 0,
        "unique_ips": 0,
        "unique_countries": 0,
        "families": [],
        "private_events": 0,
        "unresolved_events": 0,
        "q_ms": 0,
    }
    if conn is None:
        return out
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*) AS c,
                   COUNT(DISTINCT e.ip) AS ips,
                   COUNT(DISTINCT COALESCE(g.country_iso2, 'XX')) AS ccs
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
            """,
            skip_params,
        )
        row = cur.fetchone() or {}
        out["total"] = int(row.get("c") or 0)
        out["unique_ips"] = int(row.get("ips") or 0)
        out["unique_countries"] = int(row.get("ccs") or 0)
        cur.execute(
            f"""
            SELECT e.event_type, COUNT(*) AS c
            FROM pbt_security_events e
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND {skip_sql}
            GROUP BY e.event_type
            """,
            skip_params,
        )
        fams: dict[str, int] = {}
        for r in cur.fetchall() or []:
            fam = _family(r.get("event_type"))
            if fam:
                fams[fam] = fams.get(fam, 0) + int(r.get("c") or 0)
        out["families"] = [
            {"family": k, "count": v}
            for k, v in sorted(fams.items(), key=lambda kv: kv[1], reverse=True)
        ]
        cur.execute(
            f"""
            SELECT
              SUM(CASE WHEN g.country_iso2 = 'ZZ' THEN 1 ELSE 0 END) AS priv,
              SUM(CASE WHEN g.country_iso2 IS NULL OR g.country_iso2 = 'XX' THEN 1 ELSE 0 END) AS unk
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
            """,
            skip_params,
        )
        row = cur.fetchone() or {}
        out["private_events"] = int(row.get("priv") or 0)
        out["unresolved_events"] = int(row.get("unk") or 0)
        out["q_ms"] = int((time.monotonic() - t0) * 1000)
        return out
    except Exception as exc:
        print(f"[threat-map] summary_for_window: {exc}")
        out["q_ms"] = int((time.monotonic() - t0) * 1000)
        return out
    finally:
        q._close(conn)


def country_detail(iso2: str, window: str = "24h") -> dict[str, Any]:
    cc = (iso2 or "XX").strip().upper()[:2] or "XX"
    win = _window_sql(window)
    skip_sql, skip_params = _skip_sql()
    conn = q._sec()
    out = {
        "iso2": cc,
        "count": 0,
        "unique_ips": 0,
        "families": [],
        "sample_ips": [],
        "users": [],
        "last_seen": None,
    }
    if conn is None:
        return out
    try:
        cur = conn.cursor()
        if cc == "XX":
            geo_clause = "(g.ip IS NULL OR g.country_iso2 = 'XX')"
        else:
            geo_clause = "g.country_iso2 = %s"
            skip_params = list(skip_params) + [cc]
        cur.execute(
            f"""
            SELECT e.event_type, COUNT(*) AS c, COUNT(DISTINCT e.ip) AS ips,
                   MAX(COALESCE(e.created_at, e.timestamp)) AS last_seen
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
              AND {geo_clause}
            GROUP BY e.event_type
            """,
            skip_params,
        )
        fams: dict[str, int] = {}
        last = None
        ips = 0
        total = 0
        for r in cur.fetchall() or []:
            fam = _family(r.get("event_type"))
            if not fam:
                continue
            c = int(r.get("c") or 0)
            fams[fam] = fams.get(fam, 0) + c
            total += c
            ips += int(r.get("ips") or 0)
            if r.get("last_seen") and (last is None or r["last_seen"] > last):
                last = r["last_seen"]
        out["count"] = total
        out["unique_ips"] = ips
        out["last_seen"] = _fmt_ts(last) if last else None
        out["families"] = [
            {"family": k, "count": v}
            for k, v in sorted(fams.items(), key=lambda kv: kv[1], reverse=True)
        ]
        params2 = list(q._SKIP_EVENT_TYPES)
        extra = []
        if cc != "XX":
            extra = [cc]
        cur.execute(
            f"""
            SELECT e.ip, e.event_type, COALESCE(e.created_at, e.timestamp) AS created_at, e.user_id
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
              AND {geo_clause}
            ORDER BY COALESCE(e.created_at, e.timestamp) DESC
            LIMIT 12
            """,
            list(skip_params),
        )
        samples = []
        seen = set()
        for r in cur.fetchall() or []:
            ip = (r.get("ip") or "").strip()
            if not ip or ip in seen:
                continue
            seen.add(ip)
            parts = ip.split(":")
            if ":" in ip:
                mask = ":".join(parts[:3] + ["…"])
            else:
                octs = ip.split(".")
                mask = ".".join(octs[:2] + ["x", "x"]) if len(octs) == 4 else ip
            samples.append(
                {
                    "ip": mask,
                    "raw_ip": ip,
                    "user_id": r.get("user_id"),
                    "family": _family(r.get("event_type")),
                    "at": _fmt_ts(r.get("created_at")),
                }
            )
        copies = [{"user_id": s.get("user_id"), "ip": s.get("raw_ip")} for s in samples]
        _attach_usernames(copies, keep_ip=True)
        for s, c in zip(samples, copies):
            s["username"] = c.get("username")
            s.pop("raw_ip", None)
            s.pop("user_id", None)
        out["sample_ips"] = samples
        users = []
        seen_u = set()
        for s in samples:
            name = s.get("username")
            if name and name not in seen_u:
                seen_u.add(name)
                users.append({"username": name})
        out["users"] = users
        return out
    except Exception as exc:
        print(f"[threat-map] country_detail: {exc}")
        return out
    finally:
        q._close(conn)


def replay_events(window: str = "24h", *, limit: int = 400) -> dict[str, Any]:
    """Time-ordered sample for play/replay. Cap so the browser stays smooth."""
    win = _window_sql(window)
    skip_sql, skip_params = _skip_sql()
    conn = q._sec()
    out = {"events": [], "total": 0, "window": window}
    if conn is None:
        return out
    try:
        cur = conn.cursor()
        ensure_ip_geo_table(conn)
        cur.execute(
            f"""
            SELECT e.id, e.event_type, e.ip, COALESCE(e.created_at, e.timestamp) AS created_at, e.user_id,
                   COALESCE(g.country_iso2, 'XX') AS cc
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
            ORDER BY COALESCE(e.created_at, e.timestamp) ASC, e.id ASC
            """,
            skip_params,
        )
        raw = list(cur.fetchall() or [])
        need = []
        for r in raw:
            if (r.get("cc") or "XX").upper() == "XX" and (r.get("ip") or "").strip():
                need.append(r.get("ip"))
        if need:
            fill_missing_ips(conn, need, limit=min(200, len(need)))
            cur.execute(
                f"""
                SELECT e.id, e.event_type, e.ip, COALESCE(e.created_at, e.timestamp) AS created_at, e.user_id,
                       COALESCE(g.country_iso2, 'XX') AS cc
                FROM pbt_security_events e
                LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
                WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
                  AND e.ip IS NOT NULL AND e.ip != ''
                  AND {skip_sql}
                ORDER BY COALESCE(e.created_at, e.timestamp) ASC, e.id ASC
                """,
                skip_params,
            )
            raw = list(cur.fetchall() or [])
        out["total"] = len(raw)
        if len(raw) > int(limit):
            step = len(raw) / float(limit)
            picked = [raw[int(i * step)] for i in range(int(limit))]
        else:
            picked = raw
        events = []
        for r in picked:
            events.append(
                {
                    "id": int(r.get("id") or 0),
                    "family": _family(r.get("event_type")),
                    "iso2": (r.get("cc") or "XX").upper(),
                    "at": _fmt_ts(r.get("created_at")),
                    "user_id": r.get("user_id"),
                    "ip": (r.get("ip") or "").strip(),
                }
            )
        _attach_usernames(events)
        events = [
            e
            for e in events
            if not (e.get("username") and (e.get("family") or "") == "rate_limit")
        ]
        out["events"] = events
        return out
    except Exception as exc:
        print(f"[threat-map] replay_events: {exc}")
        return out
    finally:
        q._close(conn)


def recent_events(window: str = "24h", *, limit: int = 24) -> dict[str, Any]:
    """Newest hits for the Recent list. Always a real list, not animation-only."""
    win = _window_sql(window if window != "live" else "24h")
    skip_sql, skip_params = _skip_sql()
    conn = q._sec()
    out = {"events": [], "window": window if window != "live" else "24h"}
    if conn is None:
        return out
    try:
        cur = conn.cursor()
        ensure_ip_geo_table(conn)
        cur.execute(
            f"""
            SELECT e.id, e.event_type, e.ip, COALESCE(e.created_at, e.timestamp) AS created_at, e.user_id,
                   COALESCE(g.country_iso2, 'XX') AS cc
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL {win}
              AND e.ip IS NOT NULL AND e.ip != ''
              AND {skip_sql}
            ORDER BY COALESCE(e.created_at, e.timestamp) DESC, e.id DESC
            LIMIT %s
            """,
            list(skip_params) + [max(1, min(int(limit), 48))],
        )
        events = []
        for r in cur.fetchall() or []:
            events.append(
                {
                    "id": int(r.get("id") or 0),
                    "family": _family(r.get("event_type")),
                    "iso2": (r.get("cc") or "XX").upper(),
                    "at": _fmt_ts(r.get("created_at")),
                    "user_id": r.get("user_id"),
                    "ip": (r.get("ip") or "").strip(),
                }
            )
        _attach_usernames(events)
        events = [
            e
            for e in events
            if not (e.get("username") and (e.get("family") or "") == "rate_limit")
        ]
        out["events"] = events
        return out
    except Exception as exc:
        print(f"[threat-map] recent_events: {exc}")
        return out
    finally:
        q._close(conn)


def live_events(*, since_id: int = 0, limit: int = 80) -> dict[str, Any]:
    skip_sql, skip_params = _skip_sql()
    conn = q._sec()
    out = {"events": [], "max_id": int(since_id or 0)}
    if conn is None:
        return out
    try:
        cur = conn.cursor()
        ensure_ip_geo_table(conn)
        params = list(skip_params)
        id_sql = ""
        # Once the map is armed, follow id — not a 15-minute cutoff —
        # so a hit while the tab is in the background still arrives.
        if since_id:
            id_sql = "AND e.id > %s"
            params.append(int(since_id))
            time_sql = "COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL 1 DAY"
        else:
            time_sql = "COALESCE(e.created_at, e.timestamp) >= NOW() - INTERVAL 15 MINUTE"
        cur.execute(
            f"""
            SELECT e.id, e.event_type, e.ip, COALESCE(e.created_at, e.timestamp) AS created_at, e.user_id,
                   COALESCE(g.country_iso2, 'XX') AS cc
            FROM pbt_security_events e
            LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
            WHERE {time_sql}
              AND {skip_sql}
              {id_sql}
            ORDER BY e.id ASC
            LIMIT %s
            """,
            params + [int(limit)],
        )
        rows = []
        max_id = int(since_id or 0)
        need_fill = []
        for r in cur.fetchall() or []:
            eid = int(r.get("id") or 0)
            if eid > max_id:
                max_id = eid
            cc = (r.get("cc") or "XX").upper()
            ip = (r.get("ip") or "").strip()
            if cc == "XX" and ip:
                need_fill.append(ip)
            rows.append(
                {
                    "id": eid,
                    "family": _family(r.get("event_type")),
                    "iso2": cc,
                    "at": _fmt_ts(r.get("created_at")),
                    "user_id": r.get("user_id"),
                    "ip": ip,
                }
            )
        if need_fill:
            fill_missing_ips(conn, need_fill, limit=80)
            # re-stamp XX with just-resolved values
            for ev in rows:
                if ev["iso2"] != "XX":
                    continue
        # second pass for newly filled
        if need_fill:
            ph = ",".join(["%s"] * len(need_fill))
            cur.execute(
                f"SELECT ip, country_iso2 FROM pbt_ip_geo WHERE ip IN ({ph})",
                need_fill,
            )
            geo = {
                (r.get("ip") if isinstance(r, dict) else r[0]): (
                    r.get("country_iso2") if isinstance(r, dict) else r[1]
                )
                for r in (cur.fetchall() or [])
            }
            # we didn't keep ip on events for privacy — re-query those ids
            ids = [e["id"] for e in rows if e["iso2"] == "XX"]
            if ids:
                ph = ",".join(["%s"] * len(ids))
                cur.execute(
                    f"""
                    SELECT e.id, COALESCE(g.country_iso2, 'XX') AS cc
                    FROM pbt_security_events e
                    LEFT JOIN pbt_ip_geo g ON g.ip = e.ip
                    WHERE e.id IN ({ph})
                    """,
                    ids,
                )
                by_id = {int(r["id"]): (r.get("cc") or "XX").upper() for r in (cur.fetchall() or [])}
                for ev in rows:
                    if ev["id"] in by_id:
                        ev["iso2"] = by_id[ev["id"]]
        _attach_usernames(rows)
        rows = [
            e
            for e in rows
            if not (e.get("username") and (e.get("family") or "") == "rate_limit")
        ]
        out["events"] = rows
        out["max_id"] = max_id
        return out
    except Exception as exc:
        print(f"[threat-map] live_events: {exc}")
        return out
    finally:
        q._close(conn)
