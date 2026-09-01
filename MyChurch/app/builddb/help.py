# app/builddb/help.py
# Help Center: categories, articles, and user pins.

DEFAULT_CATEGORIES = [
    ('home', 'Home', 'Dashboard and getting around the site.', 10),
    ('community', 'Community', 'Events, prayers, sermons, and shared content.', 20),
    ('church-office', 'Church Office', 'Members, donations, bills, inventory, attendance, groups.', 30),
    ('my-stuff', 'My Stuff', 'Profile, security, and personal settings.', 40),
    ('admin', 'Admin', 'Pastoral tools, moderation, and church administration.', 50),
    ('account-login', 'Account & Login', 'Signing up, logging in, and account recovery.', 60),
]

WELCOME_ARTICLE = {
    'slug': 'welcome-to-help',
    'title': 'Welcome to Help & How-To Guides',
    'summary': 'How to find answers, pin guides you use often, and (for editors) manage help content.',
    'body_md': """## What this is for

The Help section is your church's own instruction library. Look up how to do everyday tasks - check in, submit a prayer, record a donation, and more.

## Find a guide

1. Open **My Stuff -> Help** from the top menu.
2. Use **Browse** to explore by category.
3. Use **Search** and type a keyword (for example: `password`, `event`, `donation`).
4. Open any guide to read the full steps.

## Pin guides you use often

On any guide page, click **Pin to my list**. Pinned guides appear at the top under the **Pinned** tab so you can find them quickly next time.

## For church leaders who edit help content

If you have the **manage help** permission, open **Manage Help Content** from the Help menu. There you can:

1. Add or edit **categories** (the folders users browse).
2. Add or edit **guides** with step-by-step instructions.
3. Choose whether a guide is published or hidden.
4. Optionally limit a guide to users with a specific permission (for staff-only topics).

Write instructions in plain language. Use numbered steps. Name the exact buttons and menu items people will see.""",
    'sort_order': 0,
}


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS help_categories (
            id              INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            slug            VARCHAR(80) NOT NULL UNIQUE,
            name            VARCHAR(120) NOT NULL,
            description     VARCHAR(500) NULL,
            sort_order      INT NOT NULL DEFAULT 0,
            is_published    TINYINT(1) NOT NULL DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_help_cat_sort (is_published, sort_order, name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS help_articles (
            id              INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            category_id     INT UNSIGNED NULL,
            slug            VARCHAR(120) NOT NULL UNIQUE,
            title           VARCHAR(255) NOT NULL,
            summary         VARCHAR(500) NULL,
            body_md         MEDIUMTEXT NOT NULL,
            permission_key  VARCHAR(64) NULL,
            sort_order      INT NOT NULL DEFAULT 0,
            is_published    TINYINT(1) NOT NULL DEFAULT 1,
            created_by      INT UNSIGNED NULL,
            updated_by      INT UNSIGNED NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_help_article_cat (category_id, is_published, sort_order),
            FOREIGN KEY (category_id) REFERENCES help_categories(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    if not _column_exists(cursor, 'help_articles', 'category_id'):
        try:
            cursor.execute(
                "ALTER TABLE help_articles ADD COLUMN category_id INT UNSIGNED NULL AFTER id"
            )
            cursor.execute(
                "ALTER TABLE help_articles ADD INDEX idx_help_article_cat (category_id, is_published, sort_order)"
            )
        except Exception:
            pass

    for legacy_col in ('nav_area', 'module_key'):
        if _column_exists(cursor, 'help_articles', legacy_col):
            try:
                cursor.execute(f"ALTER TABLE help_articles DROP COLUMN {legacy_col}")
            except Exception:
                pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_help_pins (
            id          INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id     INT UNSIGNED NOT NULL,
            article_id  INT UNSIGNED NOT NULL,
            pinned_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_article (user_id, article_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (article_id) REFERENCES help_articles(id) ON DELETE CASCADE,
            INDEX idx_pins_user (user_id, pinned_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cursor.execute("SELECT COUNT(*) FROM help_categories")
    row = cursor.fetchone()
    cat_count = row[0] if row else 0
    if cat_count == 0:
        for slug, name, desc, sort_order in DEFAULT_CATEGORIES:
            cursor.execute(
                """
                INSERT INTO help_categories (slug, name, description, sort_order)
                VALUES (%s, %s, %s, %s)
                """,
                (slug, name, desc, sort_order),
            )
        print(f"[help] Seeded {len(DEFAULT_CATEGORIES)} help categories.")

    cursor.execute("SELECT COUNT(*) FROM help_articles")
    row = cursor.fetchone()
    art_count = row[0] if row else 0
    if art_count == 0:
        cursor.execute("SELECT id FROM help_categories WHERE slug = 'home' LIMIT 1")
        home_row = cursor.fetchone()
        home_id = home_row[0] if home_row else None
        article = WELCOME_ARTICLE
        cursor.execute(
            """
            INSERT INTO help_articles
                (category_id, slug, title, summary, body_md, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                home_id,
                article['slug'],
                article['title'],
                article['summary'],
                article['body_md'],
                article['sort_order'],
            ),
        )
        print("[help] Seeded welcome help article.")