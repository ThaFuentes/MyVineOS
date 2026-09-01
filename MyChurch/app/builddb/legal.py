# app/builddb/legal.py
# Creates legal_categories and legal_notices tables; seeds default categories and starter policies.


DEFAULT_CATEGORIES = (
    ('community_guidelines', 'Community Guidelines',
     'Standards for respectful participation in our online community.', 10),
    ('comment_policy', 'Comment & Content Policy',
     'How we handle comments and user-submitted content, including moderation rights.', 20),
    ('terms', 'Terms of Use',
     'General terms for using this church website and community features.', 30),
    ('privacy', 'Privacy Policy',
     'How we collect, use, and protect personal information.', 40),
    ('general', 'General Legal Notices',
     'Other legal notices and disclaimers published by the church.', 50),
)

DEFAULT_NOTICES = (
    'community_guidelines',
    'Community Guidelines',
    """Our online community exists to encourage faith, fellowship, and respectful dialogue. We ask all members and visitors to:

- Treat others with kindness, humility, and respect
- Share content that edifies and builds up the body of Christ
- Avoid harassment, hate speech, profanity, or personal attacks
- Respect privacy - do not share others' personal information without consent
- Stay on topic and contribute meaningfully to discussions

Content that violates these guidelines may be removed. Repeat violations may result in restricted access to commenting features.

These guidelines apply to comments and submissions across announcements, events, dreams, prayers, prophecies, sermons, and other community areas of this site.""",
    'comment_policy',
    'Comment & Content Policy',
    """You are welcome to participate in discussions, leave comments, and share your thoughts on our community pages. By posting content, you agree to the following:

We reserve the right to remove, edit, or hide any comment or user-submitted content for any reason or no reason, with or without prior notice.

When we moderate content, we usually explain that the material does not align with our Community Guidelines. We are not obligated to provide an explanation in every case.

We may also remove content that appears to be spam, abusive, off-topic, or harmful to our community.

By using this site, you acknowledge that moderation decisions are at the sole discretion of church leadership and designated moderators.""",
)


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS legal_categories (
            id           INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            slug         VARCHAR(64) NOT NULL UNIQUE,
            name         VARCHAR(128) NOT NULL,
            description  TEXT,
            sort_order   INT NOT NULL DEFAULT 0,
            is_system    TINYINT(1) NOT NULL DEFAULT 1,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS legal_notices (
            id           INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            category_id  INT UNSIGNED NOT NULL,
            title        VARCHAR(255) NOT NULL,
            slug         VARCHAR(128) NOT NULL,
            summary      TEXT,
            content      MEDIUMTEXT NOT NULL,
            is_active    TINYINT(1) NOT NULL DEFAULT 1,
            sort_order   INT NOT NULL DEFAULT 0,
            created_by   INT UNSIGNED,
            updated_by   INT UNSIGNED,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES legal_categories(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE KEY uq_legal_notices_slug (slug)
        ) ENGINE=InnoDB
    """)

    try:
        cursor.execute("CREATE INDEX idx_legal_notices_category ON legal_notices(category_id)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX idx_legal_notices_active ON legal_notices(is_active)")
    except Exception:
        pass

    cursor.execute("SELECT COUNT(*) FROM legal_categories")
    if cursor.fetchone()[0] == 0:
        for slug, name, description, sort_order in DEFAULT_CATEGORIES:
            cursor.execute("""
                INSERT INTO legal_categories (slug, name, description, sort_order, is_system)
                VALUES (%s, %s, %s, %s, 1)
            """, (slug, name, description, sort_order))
        print("legal.py: seeded default legal categories")

    cursor.execute("SELECT COUNT(*) FROM legal_notices")
    if cursor.fetchone()[0] == 0:
        for i in range(0, len(DEFAULT_NOTICES), 3):
            cat_slug, title, content = DEFAULT_NOTICES[i:i + 3]
            cursor.execute("SELECT id FROM legal_categories WHERE slug = %s", (cat_slug,))
            row = cursor.fetchone()
            if not row:
                continue
            cursor.execute("""
                INSERT INTO legal_notices (category_id, title, slug, content, is_active, sort_order)
                VALUES (%s, %s, %s, %s, 1, 0)
            """, (row[0], title, cat_slug, content))
        print("legal.py: seeded starter Community Guidelines and Comment Policy")