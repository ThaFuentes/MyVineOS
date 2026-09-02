# MyChurch sandbox: official church/campus pages + optional member spaces.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS church_pages (
            campus_id     INT UNSIGNED NOT NULL DEFAULT 0,
            about         TEXT NULL,
            verse         VARCHAR(255) NULL,
            hero_path     VARCHAR(255) NULL,
            updated_by    INT UNSIGNED NULL,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (campus_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_spaces (
            user_id           INT UNSIGNED PRIMARY KEY,
            about             TEXT NULL,
            favorite_verse    VARCHAR(255) NULL,
            photo_path        VARCHAR(255) NULL,
            show_to_visitors  TINYINT(1) NOT NULL DEFAULT 0,
            show_training     TINYINT(1) NOT NULL DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_member_spaces_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    try:
        cursor.execute("CREATE INDEX idx_member_spaces_visitors ON member_spaces(show_to_visitors)")
    except Exception:
        pass

    def _col(table, name, definition):
        cursor.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (table, name),
        )
        if not cursor.fetchone():
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            except Exception as exc:
                print(f"  (skip {table}.{name}: {exc})")

    for col, definition in (
        ('accent_color', "VARCHAR(7) NULL"),
        ('bg_color', "VARCHAR(7) NULL"),
        ('text_color', "VARCHAR(7) NULL"),
        ('allow_messages', "TINYINT(1) NOT NULL DEFAULT 0"),
        ('show_stats', "TINYINT(1) NOT NULL DEFAULT 0"),
        ('allow_guest_comments', "TINYINT(1) NOT NULL DEFAULT 0"),
        ('banner_path', "VARCHAR(255) NULL"),
        ('banner_pos', "VARCHAR(16) NULL"),
        ('banner_x', "TINYINT UNSIGNED NULL"),
        ('banner_y', "TINYINT UNSIGNED NULL"),
        ('hometown', "VARCHAR(160) NULL"),
        ('occupation', "VARCHAR(160) NULL"),
        ('interests', "VARCHAR(500) NULL"),
        ('show_replies', "TINYINT(1) NOT NULL DEFAULT 0"),
        ('show_church_feed', "TINYINT(1) NOT NULL DEFAULT 1"),
        ('show_follows', "TINYINT(1) NOT NULL DEFAULT 1"),
        ('show_in_directory', "TINYINT(1) NOT NULL DEFAULT 1"),
        ('page_private', "TINYINT(1) NOT NULL DEFAULT 0"),
    ):
        _col('member_spaces', col, definition)

    for col, definition in (
        ('accent_color', "VARCHAR(7) NULL"),
        ('bg_color', "VARCHAR(7) NULL"),
        ('text_color', "VARCHAR(7) NULL"),
        ('portrait_path', "VARCHAR(255) NULL"),
        ('banner_pos', "VARCHAR(16) NULL"),
        ('banner_x', "TINYINT UNSIGNED NULL"),
        ('banner_y', "TINYINT UNSIGNED NULL"),
    ):
        _col('church_pages', col, definition)

    _col('settings', 'member_photo_limit', "INT NOT NULL DEFAULT 12")
    _col('settings', 'church_photo_limit', "INT NOT NULL DEFAULT 0")
    _col('settings', 'ai_content_monitor_enabled', "TINYINT(1) NOT NULL DEFAULT 0")
    _col('settings', 'ai_monitor_images_enabled', "TINYINT(1) NOT NULL DEFAULT 0")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS page_links (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            owner_type VARCHAR(16) NOT NULL,
            owner_id INT UNSIGNED NOT NULL DEFAULT 0,
            kind VARCHAR(24) NOT NULL DEFAULT 'website',
            title VARCHAR(255) NOT NULL,
            url VARCHAR(1000) NULL,
            note TEXT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_page_links_owner (owner_type, owner_id, kind)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS page_photos (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            owner_type VARCHAR(16) NOT NULL,
            owner_id INT UNSIGNED NOT NULL DEFAULT 0,
            filename VARCHAR(255) NOT NULL,
            caption VARCHAR(255) NULL,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_page_photos_owner (owner_type, owner_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS page_photo_comments (
            id               INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            photo_id         INT UNSIGNED NOT NULL,
            comment          TEXT NOT NULL,
            date_added       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id          INT UNSIGNED NULL,
            contributor_name VARCHAR(255) NULL,
            ip_address       VARCHAR(45) NULL,
            parent_id        INT UNSIGNED NULL,
            INDEX idx_page_photo_comments_photo (photo_id),
            CONSTRAINT fk_page_photo_comments_photo
                FOREIGN KEY (photo_id) REFERENCES page_photos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_follows (
            follower_id INT UNSIGNED NOT NULL,
            followed_id INT UNSIGNED NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (follower_id, followed_id),
            INDEX idx_user_follows_followed (followed_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_blocks (
            blocker_id INT UNSIGNED NOT NULL,
            blocked_id INT UNSIGNED NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (blocker_id, blocked_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dm_threads (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_low INT UNSIGNED NOT NULL,
            user_high INT UNSIGNED NOT NULL,
            last_read_at_low DATETIME NULL,
            last_read_at_high DATETIME NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_dm_pair (user_low, user_high)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    _col('dm_threads', 'thread_kind', "VARCHAR(16) NOT NULL DEFAULT 'direct'")
    _col('dm_threads', 'campus_id', "INT UNSIGNED NOT NULL DEFAULT 0")
    _col('dm_threads', 'starter_id', "INT UNSIGNED NULL")
    try:
        cursor.execute("ALTER TABLE dm_threads DROP INDEX uq_dm_pair")
    except Exception:
        pass
    try:
        cursor.execute(
            "ALTER TABLE dm_threads ADD UNIQUE KEY uq_dm_thread "
            "(thread_kind, campus_id, user_low, user_high)"
        )
    except Exception:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dm_messages (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            thread_id INT UNSIGNED NOT NULL,
            sender_id INT UNSIGNED NOT NULL,
            body_enc TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_dm_thread (thread_id, id),
            CONSTRAINT fk_dm_thread FOREIGN KEY (thread_id) REFERENCES dm_threads(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    _col('dm_threads', 'title', "VARCHAR(160) NULL")
    _col('dm_threads', 'created_by', "INT UNSIGNED NULL")
    _col('dm_threads', 'join_policy', "VARCHAR(16) NOT NULL DEFAULT 'invite'")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dm_members (
            thread_id     INT UNSIGNED NOT NULL,
            user_id       INT UNSIGNED NOT NULL,
            status        VARCHAR(16) NOT NULL DEFAULT 'invited',
            role          VARCHAR(16) NOT NULL DEFAULT 'member',
            last_read_at  DATETIME NULL,
            notify_push   TINYINT(1) NOT NULL DEFAULT 1,
            notify_email  TINYINT(1) NOT NULL DEFAULT 0,
            joined_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (thread_id, user_id),
            INDEX idx_dm_members_user (user_id, status),
            CONSTRAINT fk_dm_members_thread
                FOREIGN KEY (thread_id) REFERENCES dm_threads(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id         INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id    INT UNSIGNED NOT NULL,
            endpoint   VARCHAR(700) NOT NULL,
            p256dh     VARCHAR(255) NOT NULL,
            auth       VARCHAR(128) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_push_endpoint (endpoint(255)),
            INDEX idx_push_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_posts (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id INT UNSIGNED NOT NULL,
            kind VARCHAR(20) NOT NULL DEFAULT 'post',
            title VARCHAR(255) NOT NULL,
            body TEXT NULL,
            url VARCHAR(1000) NULL,
            visibility VARCHAR(20) NOT NULL DEFAULT 'public',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_community_posts_user (user_id, created_at),
            INDEX idx_community_posts_kind (kind, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    _col('community_posts', 'image_path', "VARCHAR(255) NULL")
    _col('community_posts', 'removed_at', "DATETIME NULL")
    _col('community_posts', 'removed_by', "INT UNSIGNED NULL")
    _col('community_posts', 'shadowed', "TINYINT(1) NOT NULL DEFAULT 0")
    _col('community_posts', 'shadowed_at', "DATETIME NULL")
    _col('community_posts', 'shadowed_by', "INT UNSIGNED NULL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_badges (
            id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id INT UNSIGNED NOT NULL,
            series_id INT UNSIGNED NOT NULL,
            badge_kind VARCHAR(24) NOT NULL DEFAULT 'started',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_member_badge (user_id, series_id, badge_kind)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_posting (
            content_type VARCHAR(32) NOT NULL,
            content_id INT UNSIGNED NOT NULL,
            posted_as VARCHAR(16) NOT NULL DEFAULT 'member',
            campus_id INT UNSIGNED NOT NULL DEFAULT 0,
            user_id INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (content_type, content_id),
            INDEX idx_content_posting_as (posted_as, campus_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS church_page_editors (
            campus_id INT UNSIGNED NOT NULL DEFAULT 0,
            user_id INT UNSIGNED NOT NULL,
            editor_role VARCHAR(16) NOT NULL DEFAULT 'editor',
            added_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (campus_id, user_id),
            INDEX idx_page_editors_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
