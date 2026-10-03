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
    undo_plan,
    validate_post,
)


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
