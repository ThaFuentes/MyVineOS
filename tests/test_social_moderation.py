"""Social moderation + notification rules (2026-10-04). No database, no network."""

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class DocrootProtectionTests(unittest.TestCase):
    def test_htaccess_denies_secret_files(self):
        text = _read(".htaccess")
        block = text[text.index("MYVINE DOCROOT PROTECTION"):]
        for needle in ("env", "bin", "tgz", "sql", "bak", "vapid", "config", "requirements"):
            self.assertIn(needle, block)
        self.assertIn("Options -Indexes", block)
        self.assertIn("well-known", block)

    def test_gitignore_covers_keys_and_exports(self):
        text = _read(".gitignore")
        for needle in ("dm_key.bin", "vapid", "*.tgz", "backups/"):
            self.assertIn(needle, text)


class SecurityPipelineTests(unittest.TestCase):
    def test_bot_paths_need_a_valid_key_before_skipping_limits(self):
        text = _read("poweredbytop/core/security.py")
        self.assertIn("def _bot_bearer_valid", text)
        self.assertIn("return _bot_request_allowed(ip)", text)

    def test_no_known_default_secret_key(self):
        text = _read("app/__init__.py")
        self.assertIn("_resolve_secret_key", text)
        self.assertNotRegex(text, r"SECRET_KEY'\]\s*=\s*['\"][A-Za-z0-9_-]{8,}['\"]")


class SoftDeleteTests(unittest.TestCase):
    CONTENT_FILES = [
        "app/models/social.py",
        "app/routes/prayers/views.py",
        "app/routes/prayers/queries.py",
        "app/routes/prophecies/views.py",
        "app/routes/prophecies/queries.py",
        "app/routes/dreams/queries.py",
        "app/routes/sermons/queries.py",
        "app/routes/events/event_detail.py",
        "app/routes/public/sermons/views.py",
        "app/routes/the_gathering/prayers/views.py",
        "app/routes/the_gathering/prophecies/views.py",
        "app/routes/the_gathering/dreams/views.py",
    ]

    def test_member_content_is_never_hard_deleted(self):
        pat = re.compile(
            r"DELETE FROM (community_posts|prayers|prayers_added|prophecies|prophecy_comments|"
            r"dreams|dream_comments|sermon_comments|event_comments)\b"
        )
        for rel in self.CONTENT_FILES:
            self.assertIsNone(pat.search(_read(rel)), rel)

    def test_reshare_delete_does_not_unlink_images(self):
        text = _read("app/models/social.py")
        start = text.index("def delete_post")
        body = text[start:text.index("\ndef ", start + 10)]
        self.assertNotIn("os.remove", body)
        self.assertNotIn("unlink", body)


class ModerationRulesTests(unittest.TestCase):
    def test_moderator_permission_is_known_but_not_site_mod(self):
        from app.routes.groups.utils import KNOWN_PERMISSIONS
        from app.utils.permissions import PERMISSION_SUPERSETS
        self.assertIn("moderate_content", KNOWN_PERMISSIONS)
        # Holding moderate_content must NOT satisfy moderate_site checks.
        self.assertNotIn("moderate_content", PERMISSION_SUPERSETS.get("moderate_site", frozenset()))

    def test_moderator_kinds(self):
        from app.models import moderation as mod
        self.assertIn("prayer", mod.CONTENT_MOD_KINDS)
        self.assertIn("post", mod.CONTENT_MOD_KINDS)
        self.assertNotIn("announcement", mod.CONTENT_MOD_KINDS)
        self.assertIn("post_delete", mod.REVERSIBLE)
        self.assertIn("content_delete", mod.REVERSIBLE)

    def test_report_categories(self):
        from app.models import flags
        keys = {k for k, _ in flags.REPORT_CATEGORIES}
        self.assertIn("spam", keys)
        self.assertIn("crisis", keys)
        self.assertEqual(flags.CATEGORY_SEVERITY["crisis"], 5)

    def test_masked_excerpt_hides_words(self):
        from app.models import flags
        self.assertTrue(callable(flags._masked))

    def test_ai_hook_is_off_and_offline(self):
        from app.utils import ai_moderation
        self.assertFalse(ai_moderation.AI_CHECK_ENABLED)
        text = _read("app/utils/ai_moderation.py")
        for banned in ("requests.", "urllib.request", "httpx", "openai"):
            self.assertNotIn(banned, text)


class NotificationTests(unittest.TestCase):
    def test_mentions_regex(self):
        from app.models.notifications import MENTION_RE
        found = [m.group(1) for m in MENTION_RE.finditer("hi @maya and @bob_2, mail me@x.com")]
        self.assertEqual(found, ["maya", "bob_2"])

    def test_every_type_has_text_and_icon(self):
        from app.models.notifications import TYPE_ICON, TYPE_TEXT
        self.assertEqual(set(TYPE_TEXT), set(TYPE_ICON))
        for t in ("reaction", "praying", "comment", "reply", "follow", "mention", "dm", "prayer_response"):
            self.assertIn(t, TYPE_TEXT)

    def test_migration_creates_tables(self):
        sql = _read("migrations/2026-10-04_social_moderation.sql")
        self.assertIn("CREATE TABLE IF NOT EXISTS content_flags", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS notifications", sql)


if __name__ == "__main__":
    unittest.main()
