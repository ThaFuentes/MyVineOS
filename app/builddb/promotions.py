# Church promotions / partners (missionaries, prophets, ministry sites).
# Public + member showcase cards with optional image, text, and link.

def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS church_promotions (
            id              INT PRIMARY KEY AUTO_INCREMENT,
            title           VARCHAR(200) NOT NULL,
            subtitle        VARCHAR(255) NULL,
            body_text       MEDIUMTEXT NULL,
            image_path      VARCHAR(255) NULL,
            link_url        VARCHAR(500) NULL,
            link_label      VARCHAR(120) NULL,
            badge           VARCHAR(80) NULL,
            is_published    TINYINT(1) NOT NULL DEFAULT 1,
            sort_order      INT NOT NULL DEFAULT 0,
            created_by      INT NULL,
            updated_by      INT NULL,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_promo_pub_sort (is_published, sort_order),
            INDEX idx_promo_sort (sort_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Page header text lives on settings (optional — only shown when filled)
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
    """)
    cols = {row[0] for row in cursor.fetchall()}
    for col, defn in (
        ('promotions_page_title', "VARCHAR(200) NULL"),
        ('promotions_page_intro', "MEDIUMTEXT NULL"),
    ):
        if col not in cols:
            try:
                cursor.execute(f"ALTER TABLE settings ADD COLUMN {col} {defn}")
                print(f"Migration: added settings.{col}")
            except Exception as e:
                print(f"Migration settings.{col}: {e}")

    print("Church promotions table ready.")
