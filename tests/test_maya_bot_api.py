"""Maya's church API and the Owner checklist. No database.

MySQL settings are pointed at 127.0.0.1:9 (nothing listens) and the test
proves a connection fails, so nothing here can touch real church data. The
permission store is exercised against an in-memory fake cursor.
"""

import os
import unittest
from unittest.mock import patch

os.environ.update({"MYSQL_HOST": "127.0.0.1", "MYSQL_PORT": "9", "MYSQL_USER": "maya_test_nobody",
                   "MYSQL_PASSWORD": "not-a-real-password", "MYSQL_DATABASE": "maya_test_nodb"})

from flask import Flask  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from app.utils import maya_perms  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.perms = {}  # (key_id, perm) -> {"enabled": 0/1, "expires_at": datetime|None}
        self.log = []
        self._rows = []
        self.lastrowid = 1

    def execute(self, sql, args=()):
        s = " ".join(sql.split())
        if s.startswith("SELECT perm, enabled, expires_at FROM maya_bot_permissions"):
            self._rows = [{"perm": p, **v} for (k, p), v in self.perms.items() if k == args[0]]
        elif s.startswith("SELECT key_id, perm FROM maya_bot_permissions"):
            self._rows = [{"key_id": k, "perm": p} for (k, p), v in self.perms.items()
                          if v["enabled"] and v["expires_at"] is not None and v["expires_at"] <= args[0]]
        elif s.startswith("INSERT INTO maya_bot_permissions"):
            self.perms[(args[0], args[1])] = {"enabled": args[2], "expires_at": args[3]}
        elif s.startswith("UPDATE maya_bot_permissions SET enabled=0"):
            self.perms[(args[0], args[1])] = {"enabled": 0, "expires_at": None}
        elif s.startswith("INSERT INTO maya_bot_perm_log"):
            self.log.append(args)
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


OWNER = {"id": 1, "role": "Owner", "password": generate_password_hash("Right-pass-123"), "totp_enabled": 0}
MAYA_ROW = {"id": 5, "active": True, "name": "Maya", "created_by": 9, "voices": []}


class DeadDatabase(unittest.TestCase):
    def test_cannot_connect(self):
        import pymysql

        with self.assertRaises(Exception):
            pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]),
                            user="x", password="y", connect_timeout=2)

    def test_get_db_uses_dead_address(self):
        from app.models.db import get_db

        app = Flask(__name__)
        app.config.update(MYSQL_HOST="127.0.0.1", MYSQL_PORT=9, MYSQL_USER="x", MYSQL_PASSWORD="y",
                          MYSQL_DATABASE="z")
        with app.app_context(), self.assertRaises(Exception):
            get_db()


class Catalog(unittest.TestCase):
    def test_granular(self):
        ids = set(maya_perms.CATALOG_BY_ID)
        for pid in ("announcements.read", "announcements.create", "announcements.edit", "announcements.publish",
                    "announcements.delete", "announcements.restore", "prayers.approve", "events.publish",
                    "wall.create", "comments.restore", "moderation.review", "builder.edit", "lineup.edit"):
            self.assertIn(pid, ids)

    def test_defaults_and_high_risk(self):
        for p in maya_perms.CATALOG:
            self.assertEqual(p["default"], not p["high_risk"], p["id"])
        high = {p["id"] for p in maya_perms.CATALOG if p["high_risk"]}
        for pid in ("users.role", "users.ban", "settings.security", "giving.write", "hard_delete", "members.contact"):
            self.assertIn(pid, high)

    def test_hard_limits(self):
        text = " ".join(maya_perms.HARD_LIMITS).lower()
        self.assertIn("checklist", text)
        self.assertIn("password hashes", text)


class SaveState(unittest.TestCase):
    def setUp(self):
        self.cur = FakeCursor()
        self.p = patch.object(maya_perms, "_cur", return_value=self.cur)
        self.p.start()
        self.lc = patch("app.models.log.log_change")
        self.lc.start()

    def tearDown(self):
        self.p.stop()
        self.lc.stop()

    def test_defaults(self):
        state = maya_perms.perm_state(5)
        self.assertTrue(state["announcements.create"])
        self.assertFalse(state["hard_delete"])
        self.assertFalse(state["settings.security"])

    def test_toggle_live(self):
        changed, refused = maya_perms.save_state(5, {"announcements.create": False}, owner=OWNER, confirmed_with=None)
        self.assertEqual((changed, refused), (["announcements.create"], []))
        self.assertFalse(maya_perms.perm_state(5)["announcements.create"])
        self.assertEqual(len(self.cur.log), 1)

    def test_high_risk_needs_confirm(self):
        _c, refused = maya_perms.save_state(5, {"hard_delete": True}, owner=OWNER, confirmed_with=None)
        self.assertEqual(refused, ["hard_delete"])
        self.assertFalse(maya_perms.perm_state(5)["hard_delete"])
        changed, _r = maya_perms.save_state(5, {"hard_delete": True}, owner=OWNER, confirmed_with="password")
        self.assertEqual(changed, ["hard_delete"])
        self.assertTrue(maya_perms.perm_state(5)["hard_delete"])
        self.assertEqual(self.cur.log[-1][6], "password,timer")

    def test_unimplemented_stays_off(self):
        maya_perms.save_state(5, {"settings.security": True}, owner=OWNER, confirmed_with="totp")
        self.assertFalse(maya_perms.perm_state(5)["settings.security"])

    def test_only_owner_saves(self):
        with self.assertRaises(PermissionError):
            maya_perms.save_state(5, {"wall.read": False}, owner={"id": 9, "role": "Admin"}, confirmed_with="password")

    def test_forbidden_never_allowed(self):
        with patch.object(maya_perms, "is_maya", return_value=True):
            for pid in maya_perms.FORBIDDEN_IDS:
                self.assertFalse(maya_perms.allowed(MAYA_ROW, pid))

    def test_high_risk_timer_required_default_24h(self):
        from datetime import datetime, timedelta

        maya_perms.save_state(5, {"giving.read": True}, owner=OWNER, confirmed_with="password")
        exp = maya_perms.perm_expiry(5)["giving.read"]
        self.assertAlmostEqual((exp - datetime.utcnow()).total_seconds(), 86400, delta=120)
        with patch.object(maya_perms, "is_maya", return_value=True):
            caps = maya_perms.capabilities({"id": 5})
        entry = [p for g in caps["groups"] for p in g["permissions"] if p["id"] == "giving.read"][0]
        self.assertTrue(entry["expires_at"].endswith("Z"))
        self.assertTrue(entry["timer_required"])
        _c, refused = maya_perms.save_state(5, {"giving.read": True}, owner=OWNER, confirmed_with=None,
                                            expiry={"giving.read": datetime.utcnow() + timedelta(days=60)})
        self.assertEqual(refused, ["giving.read"])

    def test_expired_is_off_live_and_lazily_flipped(self):
        from datetime import datetime, timedelta

        maya_perms.save_state(5, {"wall.read": True}, owner=OWNER, confirmed_with=None,
                              expiry={"wall.read": datetime.utcnow() + timedelta(hours=1)})
        self.assertTrue(maya_perms.perm_state(5)["wall.read"])
        self.cur.perms[(5, "wall.read")]["expires_at"] = datetime.utcnow() - timedelta(seconds=1)
        self.assertFalse(maya_perms.perm_state(5, cleanup=False)["wall.read"])
        self.assertEqual(self.cur.perms[(5, "wall.read")]["enabled"], 1)
        self.assertFalse(maya_perms.perm_state(5)["wall.read"])
        self.assertEqual(self.cur.perms[(5, "wall.read")]["enabled"], 0)
        self.assertEqual(self.cur.log[-1][6], "auto-expired")

    def test_cron_and_parse(self):
        from datetime import datetime, timedelta

        maya_perms.save_state(5, {"events.read": True}, owner=OWNER, confirmed_with=None,
                              expiry={"events.read": maya_perms.parse_expiry("weeks", 1)})
        self.assertEqual(maya_perms.expire_due(now=datetime.utcnow() + timedelta(days=8)), 1)
        self.assertEqual(self.cur.perms[(5, "events.read")]["enabled"], 0)
        self.assertIsNone(maya_perms.parse_expiry("none", 3))
        with self.assertRaises(ValueError):
            maya_perms.parse_expiry("days", 0)

    def test_confirm_owner(self):
        self.assertEqual(maya_perms.confirm_owner(OWNER, "Right-pass-123"), "password")
        self.assertIsNone(maya_perms.confirm_owner(OWNER, "wrong"))
        self.assertIsNone(maya_perms.confirm_owner({**OWNER, "role": "Admin"}, "Right-pass-123"))


class Gate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.routes import maya_api

        cls.mod = maya_api
        cls.app = Flask(__name__)
        cls.app.secret_key = "tests"
        cls.app.register_blueprint(maya_api.maya_api_bp)
        from flask import Blueprint

        auth = Blueprint("auth", __name__)
        auth.add_url_rule("/login", "login", lambda: "login")
        cls.app.register_blueprint(auth)

    def _post(self, path, maya=True, on=True):
        from app.routes import bot_access as ba

        with patch.object(ba, "_require_key", return_value=(dict(MAYA_ROW), None)), \
                patch.object(self.mod.store, "write_log", return_value=1), \
                patch.object(maya_perms, "is_maya", return_value=maya), \
                patch.object(maya_perms, "allowed", return_value=on), \
                patch.object(maya_perms, "acting_user_id", return_value=9):
            return self.app.test_client().post(path, json={})

    def test_routes_registered(self):
        rules = {r.rule for r in self.app.url_map.iter_rules()}
        for path in ("/api/bot/maya/capabilities", "/api/bot/maya/announcements", "/api/bot/maya/prayers",
                     "/api/bot/maya/events", "/api/bot/maya/posts", "/api/bot/maya/moderation/removed",
                     "/api/bot/maya/builder/sermons", "/settings/maya-permissions"):
            self.assertIn(path, rules)

    def test_route_perms_in_catalog_and_no_secret_paths(self):
        for r in self.mod.MAYA_ROUTES:
            if r["perm"]:
                self.assertIn(r["perm"], maya_perms.CATALOG_BY_ID, r)
            for bad in ("permission", "secret", "password_hash", "/keys"):
                self.assertNotIn(bad, r["path"].lower())

    def test_not_maya(self):
        res = self._post("/api/bot/maya/prayers/3/restore", maya=False)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["data"]["code"], "not_maya")

    def test_switch_off(self):
        res = self._post("/api/bot/maya/prayers/3/restore", on=False)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["data"]["code"], "permission_off")

    def test_hard_delete_needs_confirm_word(self):
        res = self._post("/api/bot/maya/announcements/3/destroy")
        self.assertEqual(res.status_code, 400)
        self.assertIn("DELETE", res.get_json()["error"])

    def test_users_hard_limits(self):
        from app.routes import bot_access as ba

        for target in ({"id": 9, "role": "Member"}, {"id": 2, "role": "Owner"}, {"id": 3, "role": "Admin"}):
            with patch("app.models.users.get_user_by_id", return_value=target), \
                    patch.object(ba, "_require_key", return_value=(dict(MAYA_ROW), None)), \
                    patch.object(self.mod.store, "write_log", return_value=1), \
                    patch.object(maya_perms, "is_maya", return_value=True), \
                    patch.object(maya_perms, "allowed", return_value=True), \
                    patch.object(maya_perms, "acting_user_id", return_value=9):
                res = self.app.test_client().post(f"/api/bot/maya/users/{target['id']}/ban", json={"banned": True})
            self.assertEqual(res.status_code, 403, target)
            self.assertEqual(res.get_json()["data"]["code"], "hard_limit")

    def test_owner_page_refuses_non_owner(self):
        res = self.app.test_client().get("/settings/maya-permissions")
        self.assertIn(res.status_code, (302, 401, 403))
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["user_role"] = "Admin"
        with patch("app.routes.bot_access.get_user_by_id", return_value={"id": 3, "role": "Admin"}):
            self.assertEqual(client.get("/settings/maya-permissions").status_code, 403)
            self.assertEqual(client.post("/settings/maya-permissions", data={"perm": "hard_delete"}).status_code, 403)


class EventForm(unittest.TestCase):
    def test_partial_edit_keeps_fields(self):
        from app.routes.maya_api import _form
        from app.services.church_events import row_as_form

        base = row_as_form({"event_name": "Picnic", "event_date": "2026-11-01", "potluck_enabled": 1,
                            "payment_option_ids": "2,3", "location": "Park", "capacity": None})
        merged = _form({"location": "Hall"}, base)
        self.assertEqual(merged.get("event_name"), "Picnic")
        self.assertEqual(merged.get("location"), "Hall")
        self.assertIn("potluck_enabled", merged)
        self.assertEqual(merged.getlist("payment_option_ids"), ["2", "3"])


if __name__ == "__main__":
    unittest.main()
