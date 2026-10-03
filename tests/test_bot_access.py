"""Rules for the church bot. No database."""

import unittest

from app.utils.bot_policy import (
    CLOSED,
    READS,
    SWITCHES,
    default_controls,
    hash_key,
    help_payload,
    new_key_material,
    normalize_controls,
    resolve_voice,
    switch_on,
    undo_label,
    undo_plan,
    validate_post,
)
from app.utils.bot_sermons import as_html, assignments_with_speaker, verse_span


class BotPolicyTests(unittest.TestCase):
    def test_switches_start_off(self):
        controls = default_controls()
        self.assertTrue(controls)
        self.assertFalse(any(controls.values()))
        self.assertEqual(set(controls), {row["id"] for row in SWITCHES})

    def test_unknown_switch_is_dropped(self):
        controls = normalize_controls({"posts": True, "passwords": True, "child_checkin": 1})
        self.assertTrue(controls["posts"])
        self.assertNotIn("passwords", controls)
        self.assertNotIn("child_checkin", controls)
        self.assertFalse(controls["security"])

    def test_church_voice_needs_an_author_and_a_grant(self):
        missing, err = resolve_voice("church", [])
        self.assertIsNone(missing)
        self.assertIn("church", err)
        bare, err = resolve_voice("church", [{"voice_type": "church", "user_id": None}])
        self.assertIsNone(bare)
        self.assertIn("author", err)
        voice, err = resolve_voice("church", [{"voice_type": "church", "user_id": 4}])
        self.assertIsNone(err)
        self.assertEqual(voice["posted_as"], "church")
        self.assertEqual(voice["user_id"], 4)

    def test_several_people_and_the_church_can_be_attached(self):
        voices = [
            {"voice_type": "church", "user_id": 2},
            {"voice_type": "user", "user_id": 8},
            {"voice_type": "user", "user_id": 9},
        ]
        church, _err = resolve_voice("church", voices)
        one, _err = resolve_voice("user:8", voices)
        other, err = resolve_voice("user:3", voices)
        self.assertEqual(church["as"], "church")
        self.assertEqual(one["posted_as"], "member")
        self.assertEqual(one["user_id"], 8)
        self.assertIsNone(other)
        self.assertIn("cannot post as that person", err)

    def test_verse_needs_a_body_and_reverse_is_soft(self):
        bad, err = validate_post("verse", "Psalm 23", "", "public")
        self.assertIsNone(bad)
        self.assertIn("body", err)
        good, err = validate_post("verse", "", "The Lord is my shepherd.", "nope")
        self.assertIsNone(err)
        self.assertEqual(good["kind"], "verse")
        self.assertEqual(good["title"], "Verse")
        self.assertEqual(good["visibility"], "public")
        self.assertEqual(undo_plan("post.create", False), "hide")
        self.assertEqual(undo_plan("post.create", True), "show")
        self.assertIsNone(undo_plan("denied", False))

    def test_help_lists_live_calls_and_keeps_secrets_out(self):
        payload = help_payload({"posts": True, "security": False}, [
            {"voice_type": "church", "user_id": 2, "label": "Church"},
            {"voice_type": "user", "user_id": 8, "label": "Ada"},
        ])
        text = "\n".join(payload["lines"])
        self.assertIn("GET /api/bot/help", text)
        self.assertIn("POST /api/bot/posts", text)
        self.assertIn("GET /api/bot/security", text)
        self.assertIn("GET /api/bot/read/members", text)
        self.assertIn("[on]", text)
        self.assertIn("[off]", text)
        self.assertEqual(payload["voices"][0]["as"], "church")
        self.assertEqual(payload["voices"][1]["as"], "user:8")
        joined = " ".join(payload["closed"])
        self.assertIn("check-in", joined)
        self.assertIn("Deleting", joined)
        for sql in READS.values():
            lowered = sql.lower()
            self.assertTrue(lowered.startswith("select "))
            self.assertIn("limit %s", lowered)
            self.assertNotIn("password", lowered)
            self.assertNotIn("checkin_pin", lowered)
            self.assertNotIn("account_number", lowered)
            self.assertNotIn("encrypted_", lowered)
        read_ids = {row["id"] for row in SWITCHES if row["kind"] == "read"}
        self.assertEqual(read_ids, set(READS))

    def test_key_material_and_reverse_needs_no_switch(self):
        raw, digest, prefix = new_key_material()
        self.assertTrue(raw.startswith("mvos_"))
        self.assertEqual(digest, hash_key(raw))
        self.assertEqual(prefix, raw[:14])
        self.assertTrue(switch_on({"posts": "on"}, "posts"))
        calls = {row["path"]: row for row in help_payload({})["calls"]}
        self.assertIsNone(calls["/api/bot/reverse"]["switch"])
        self.assertTrue(calls["/api/bot/reverse"]["allowed"])
        self.assertFalse(calls["/api/bot/posts"]["allowed"])

    def test_pipeline_lets_the_bot_through_without_replacing_csrf(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        security = (root / "poweredbytop" / "core" / "security.py").read_text()
        store = (root / "app" / "utils" / "bot_store.py").read_text()
        self.assertIn('path.startswith("/api/bot/")', security)
        self.assertIn("CSRF_PROTECTION", security)
        self.assertIn("removed_at", store)
        self.assertNotIn("delete_post", store)
        self.assertNotIn("DELETE FROM community_posts", store)
        self.assertTrue(CLOSED)

    def test_sermon_desk_undo_and_calls(self):
        self.assertFalse(default_controls()["sermon_builder"])
        self.assertEqual(undo_plan("sermon.create", False), "hide")
        self.assertEqual(undo_plan("sermon.create", True), "show")
        self.assertEqual(undo_plan("sermon.update", False), "restore")
        self.assertEqual(undo_plan("sermon.update", True), "reapply")
        self.assertEqual(undo_plan("section.add", False), "hide")
        self.assertEqual(undo_plan("lineup.set", False), "restore")
        self.assertEqual(undo_label("lineup.set", False), "Undo")
        self.assertEqual(undo_label("lineup.set", True), "Redo")
        self.assertEqual(undo_label("sermon.create", False), "Hide")
        off = "\n".join(help_payload({})["lines"])
        on = "\n".join(help_payload({"sermon_builder": True})["lines"])
        for path in (
            "GET /api/bot/sermons",
            "POST /api/bot/sermons",
            "POST /api/bot/illustrations",
            "GET /api/bot/vault",
            "GET /api/bot/verses",
            "GET /api/bot/lineup",
            "POST /api/bot/lineup",
        ):
            self.assertIn(path, on)
        self.assertIn("GET /api/bot/sermons [off]", off)
        self.assertIn("GET /api/bot/sermons [on]", on)
        self.assertEqual(as_html("John 3:16"), "<p>John 3:16</p>")
        self.assertIn("&lt;script&gt;", as_html("<script>alert(1)</script>"))
        self.assertTrue(as_html("<p>Already</p>").startswith("<p>Already"))
        self.assertEqual(verse_span(30, 28), (28, 30))
        self.assertIsNone(verse_span(1, 41))
        roles = assignments_with_speaker(
            [
                {"role_name": "Minister", "user_id": 2, "guest_name": None},
                {"role_name": "Greeter", "user_id": 5, "guest_name": "Pat"},
            ],
            9,
            "Guest Pat",
            True,
        )
        self.assertEqual(roles[0]["user_id"], 9)
        self.assertIsNone(roles[0]["guest_name"])
        self.assertEqual(roles[1]["user_id"], 5)
        added = assignments_with_speaker(
            [{"role_name": "Greeter", "user_id": 5, "guest_name": None}],
            None,
            "Pat",
            True,
        )
        self.assertEqual(added[-1]["role_name"], "Minister")
        self.assertEqual(added[-1]["guest_name"], "Pat")
        self.assertIsNone(added[-1]["user_id"])

    def test_two_inboxes_and_mail_stay_apart(self):
        from app.utils.bot_login import api_mail_problem, twofa_mail_problem
        from app.utils.bot_policy import (
            TWOFA_TTL_SECONDS,
            api_key_mail,
            inbox_problem,
            new_session_material,
            new_twofa_material,
            twofa_key_mail,
        )
        self.assertIn("different", inbox_problem("a@b.co", "a@b.co"))
        self.assertIn("API key", inbox_problem("nope", "two@example.com"))
        self.assertIsNone(inbox_problem("keys@example.com", "codes@example.com"))
        subject, body = api_key_mail("Helper", "mvos_testkey", "https://myvinechurch.online")
        self.assertIn("API key", subject)
        self.assertIn("api_key: mvos_testkey", body)
        self.assertIn("expires: never", body)
        self.assertNotIn("twofa_key:", body)
        self.assertNotIn("codes@example.com", body)
        self.assertIsNone(api_mail_problem(body, "codes@example.com"))
        raw, digest, prefix = new_twofa_material()
        self.assertTrue(raw.startswith("mvos_2fa_"))
        self.assertEqual(prefix, raw[:18])
        self.assertEqual(digest, hash_key(raw))
        subject, twofa_body = twofa_key_mail("Helper", raw, "https://myvinechurch.online")
        self.assertIn("2FA", subject)
        self.assertIn(f"twofa_key: {raw}", twofa_body)
        self.assertIn("expires_in: 3600", twofa_body)
        self.assertNotIn("api_key:", twofa_body)
        self.assertNotIn("keys@example.com", twofa_body)
        self.assertNotIn("mvos_testkey", twofa_body)
        self.assertIsNone(twofa_mail_problem(twofa_body, "keys@example.com"))
        self.assertEqual(TWOFA_TTL_SECONDS, 3600)
        session, _session_digest, session_prefix = new_session_material()
        self.assertTrue(session.startswith("mvos_s_"))
        self.assertEqual(session_prefix, session[:16])
        lines = "\n".join(help_payload({})["lines"])
        self.assertIn("POST /api/bot/login ", lines)
        self.assertIn("POST /api/bot/login/exchange", lines)
        self.assertIn("POST /api/bot/password-reset", lines)
        self.assertIn("X-Bot-2FA", lines)
        self.assertIn("1 hour", lines)
        sign = help_payload({})["sign_in"]
        self.assertIn("Does not expire", sign["api_key"])
        self.assertEqual(sign["twofa_header"], "X-Bot-2FA")
        self.assertEqual(sign["expires_in"], 3600)
        present = {
            "step": "twofa",
            "sent": True,
            "expires_in": 3600,
            "message": "A 2FA key was emailed to the other inbox.",
        }
        self.assertNotIn(raw, str(present))

    def test_owner_pages_mail_keys_and_keep_them_off_the_screen(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        routes = (root / "app/routes/bot_access.py").read_text()
        page = (root / "app/templates/settings/bot_access.html").read_text()
        usage = (root / "app/templates/settings/bot_usage.html").read_text()
        nav = (root / "app/templates/settings/base_settings.html").read_text()
        login = (root / "app/utils/bot_login.py").read_text()
        self.assertNotIn("bot_issued_key", routes)
        self.assertNotIn("issue_key", routes)
        self.assertIn("find_session", routes)
        self.assertIn('"/api/bot/login"', routes)
        self.assertIn('"/api/bot/login/exchange"', routes)
        self.assertIn('"/api/bot/password-reset"', routes)
        self.assertIn('"/settings/bot-access/usage"', routes)
        self.assertIn("That is the API key", routes)
        self.assertNotIn("issued_key", page)
        self.assertNotIn("Copy this key", page)
        self.assertIn('name="twofa_email"', page)
        self.assertIn("Bot usage", page)
        self.assertIn("bot_name", usage)
        self.assertIn('name="next" value="usage"', usage)
        self.assertIn("bot_access.usage", nav)
        self.assertIn("api_mail_problem", login)
        self.assertNotIn("return raw", login)

    def test_sermon_desk_does_not_hard_delete(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        names = (
            "app/utils/bot_sermons.py",
            "app/utils/bot_sermon_library.py",
            "app/utils/bot_sermon_common.py",
            "app/routes/bot_access.py",
        )
        blobs = [(root / name).read_text() for name in names]
        for blob in blobs:
            self.assertNotIn("delete_sermon", blob)
            self.assertNotIn("delete_illustration", blob)
            self.assertNotIn("save_sermon_sections", blob)
            self.assertNotIn("append_scripture_to_sermon", blob)
            self.assertNotIn("DELETE FROM pastoral_sermons", blob)
            self.assertNotIn("DELETE FROM illustration_library", blob)
            self.assertNotIn("DELETE FROM sermon_sections", blob)
            self.assertNotIn("DELETE FROM pastoral_vault", blob)
        routes = blobs[-1]
        self.assertIn('"/api/bot/sermons"', routes)
        self.assertIn('"/api/bot/verses"', routes)
        self.assertIn('"/api/bot/lineup"', routes)
        self.assertIn("sermons.apply_undo", routes)
        self.assertIn("DELETE FROM service_plans", blobs[1])
