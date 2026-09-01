# Welcome / login appearance columns + hero image gallery + featured spots.

def create_tables(cursor):
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    existing = [row[0] for row in cursor.fetchall()]

    columns = {
        'welcome_tagline': "TEXT",
        'welcome_verse': "TEXT",
        'welcome_kicker': "VARCHAR(160) NULL",
        'welcome_hero_mode': "VARCHAR(20) DEFAULT 'theme'",
        'welcome_hero_interval_sec': "INT DEFAULT 6",
        'login_hero_mode': "VARCHAR(20) DEFAULT 'theme'",
        'login_hero_interval_sec': "INT DEFAULT 8",
        'welcome_show_services': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_show_about': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_show_events': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_show_verse': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_show_featured': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_show_quick_links': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_show_ctas': "TINYINT(1) NOT NULL DEFAULT 1",
        'welcome_featured_heading': "VARCHAR(160) NULL",
        'welcome_cta1_label': "VARCHAR(80) NULL",
        'welcome_cta1_url': "VARCHAR(500) NULL",
        'welcome_cta2_label': "VARCHAR(80) NULL",
        'welcome_cta2_url': "VARCHAR(500) NULL",
    }
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {name} {definition}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_hero_images (
            id           INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            surface      VARCHAR(20) NOT NULL,
            filename     VARCHAR(255) NOT NULL,
            caption      VARCHAR(255) NULL,
            sort_order   INT NOT NULL DEFAULT 0,
            enabled      TINYINT(1) NOT NULL DEFAULT 1,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """)
    try:
        cursor.execute("CREATE INDEX idx_hero_surface ON site_hero_images(surface, enabled, sort_order)")
    except Exception:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_welcome_features (
            id           INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            title        VARCHAR(160) NOT NULL,
            body         TEXT NULL,
            filename     VARCHAR(255) NULL,
            link_url     VARCHAR(500) NULL,
            link_label   VARCHAR(80) NULL,
            sort_order   INT NOT NULL DEFAULT 0,
            enabled      TINYINT(1) NOT NULL DEFAULT 1,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
    """)
    try:
        cursor.execute("CREATE INDEX idx_welcome_features_sort ON site_welcome_features(enabled, sort_order, id)")
    except Exception:
        pass
