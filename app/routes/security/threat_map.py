# Threat map — loaded only when this module imports successfully.
from __future__ import annotations

import os

from flask import jsonify, render_template, request, session

from . import security_bp
from .utils import can_access_security_console, can_manage_security_access
from .views import security_required


def _flag_on() -> bool:
    flag = (os.getenv("CHURCH_THREAT_MAP") or os.getenv("AEGIS_THREAT_MAP") or "1").strip().lower()
    return flag not in ("0", "false", "off")


def _json_denied(code=401):
    return jsonify({"ok": False, "error": "auth"}), code


def _home_pin() -> dict:
    name = "THIS SITE"
    try:
        from flask import g

        s = getattr(g, "settings", None) or {}
        name = (s.get("church_name") or name).strip() or "THIS SITE"
    except Exception:
        pass
    try:
        lon = float(os.getenv("CHURCH_MAP_LON") or "-97.0")
        lat = float(os.getenv("CHURCH_MAP_LAT") or "38.0")
    except (TypeError, ValueError):
        lon, lat = -97.0, 38.0
    return {"lon": lon, "lat": lat, "label": name[:40]}


def threat_map_json_required(f):
    from functools import wraps

    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _flag_on():
            return jsonify({"ok": False, "error": "off"}), 404
        if not session.get("user_id"):
            return _json_denied(401)
        if not can_access_security_console():
            return _json_denied(403)
        return f(*args, **kwargs)

    return wrapped


@security_bp.route("/threat-map")
@security_required
def threat_map():
    if not _flag_on():
        from flask import abort

        abort(404)
    try:
        from .geo_lookup import ensure_ip_geo_table
        from . import queries as q

        conn = q._sec()
        if conn is not None:
            try:
                ensure_ip_geo_table(conn)
            finally:
                q._close(conn)
    except Exception as exc:
        print(f"[threat-map] table ensure: {exc}")
    return render_template(
        "security/threat_map.html",
        page_title="Threat map",
        can_manage_access=can_manage_security_access(),
        home_pin=_home_pin(),
    )


@security_bp.route("/threat-map/summary")
@threat_map_json_required
def threat_map_summary():
    from . import threat_queries as tq

    window = (request.args.get("window") or "24h").strip().lower()
    if window not in tq.WINDOWS:
        window = "24h"
    data = tq.summary_for_window(window)
    data["ok"] = True
    return jsonify(data)


@security_bp.route("/threat-map/countries")
@threat_map_json_required
def threat_map_countries():
    from . import threat_queries as tq

    window = (request.args.get("window") or "24h").strip().lower()
    if window not in tq.WINDOWS:
        window = "24h"
    data = tq.countries_for_window(window, fill=True)
    data["ok"] = True
    return jsonify(data)


@security_bp.route("/threat-map/country/<iso2>")
@threat_map_json_required
def threat_map_country(iso2):
    from . import threat_queries as tq

    window = (request.args.get("window") or "24h").strip().lower()
    if window not in tq.WINDOWS:
        window = "24h"
    data = tq.country_detail(iso2, window)
    data["ok"] = True
    return jsonify(data)


@security_bp.route("/threat-map/replay")
@threat_map_json_required
def threat_map_replay():
    from . import threat_queries as tq

    window = (request.args.get("window") or "24h").strip().lower()
    if window not in tq.WINDOWS:
        window = "24h"
    try:
        limit = int(request.args.get("limit") or 400)
    except (TypeError, ValueError):
        limit = 400
    limit = max(20, min(limit, 600))
    data = tq.replay_events(window, limit=limit)
    data["ok"] = True
    return jsonify(data)


@security_bp.route("/threat-map/recent")
@threat_map_json_required
def threat_map_recent():
    from . import threat_queries as tq

    window = (request.args.get("window") or "24h").strip().lower()
    if window not in tq.WINDOWS:
        window = "24h"
    try:
        limit = int(request.args.get("limit") or 24)
    except (TypeError, ValueError):
        limit = 24
    limit = max(8, min(limit, 48))
    data = tq.recent_events(window, limit=limit)
    data["ok"] = True
    return jsonify(data)


@security_bp.route("/threat-map/live")
@threat_map_json_required
def threat_map_live():
    from . import threat_queries as tq

    try:
        since_id = int(request.args.get("since_id") or 0)
    except (TypeError, ValueError):
        since_id = 0
    try:
        limit = int(request.args.get("limit") or 80)
    except (TypeError, ValueError):
        limit = 80
    limit = max(1, min(limit, 120))
    data = tq.live_events(since_id=since_id, limit=limit)
    data["ok"] = True
    return jsonify(data)
