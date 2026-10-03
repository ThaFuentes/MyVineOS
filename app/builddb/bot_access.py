"""Bot Access keys, posting voices, and the soft undo log.

The owner issues a key and turns switches on. Voices say who the bot may
post as. The log stores a snapshot so a post can be hidden and restored.
"""


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_access_keys (
            id            INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            name          VARCHAR(120) NOT NULL,
            key_hash      CHAR(64) NOT NULL,
            key_prefix    VARCHAR(20) NOT NULL,
            active        TINYINT(1) NOT NULL DEFAULT 1,
            controls_json TEXT NULL,
            created_by    INT UNSIGNED NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_bot_access_hash (key_hash),
            KEY idx_bot_access_active (active),
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_access_voices (
            id          INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            key_id      INT UNSIGNED NOT NULL,
            voice_type  VARCHAR(20) NOT NULL,
            user_id     INT UNSIGNED NULL,
            label       VARCHAR(160) NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_bot_voice_key (key_id),
            FOREIGN KEY (key_id) REFERENCES bot_access_keys(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_access_log (
            id            INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            key_id        INT UNSIGNED NOT NULL,
            action        VARCHAR(40) NOT NULL,
            target_type   VARCHAR(40) NULL,
            target_id     INT UNSIGNED NULL,
            ok            TINYINT(1) NOT NULL DEFAULT 0,
            detail        VARCHAR(500) NULL,
            snapshot_json TEXT NULL,
            reversed_at   DATETIME NULL,
            reversed_by   VARCHAR(80) NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_bot_log_key (key_id, id),
            FOREIGN KEY (key_id) REFERENCES bot_access_keys(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
