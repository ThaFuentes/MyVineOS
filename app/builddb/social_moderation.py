# Report queue, word-list hits, and the notification bell.
# Additive only: CREATE TABLE IF NOT EXISTS. church_id is nullable so the
# MyVineOS Cloud port only has to start filling it in.
# Same SQL is in migrations/2026-10-04_social_moderation.sql for a manual run.


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_flags (
            id                   INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            church_id            INT UNSIGNED NULL,
            content_kind         VARCHAR(32) NOT NULL,
            content_id           INT UNSIGNED NULL,
            content_table        VARCHAR(64) NULL,
            author_id            INT UNSIGNED NULL,
            source               VARCHAR(16) NOT NULL DEFAULT 'report',
            category             VARCHAR(24) NOT NULL DEFAULT 'other',
            severity             TINYINT UNSIGNED NOT NULL DEFAULT 1,
            ai_score             DECIMAL(4,3) NULL,
            ai_reason            VARCHAR(500) NULL,
            reporter_id          INT UNSIGNED NULL,
            reporter_note        VARCHAR(500) NULL,
            excerpt              VARCHAR(500) NULL,
            context              VARCHAR(160) NULL,
            status               VARCHAR(16) NOT NULL DEFAULT 'open',
            resolved_by          INT UNSIGNED NULL,
            resolved_at          DATETIME NULL,
            moderation_action_id INT UNSIGNED NULL,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_content_flags_report (content_kind, content_id, source, reporter_id),
            INDEX idx_content_flags_status (status, severity, created_at),
            INDEX idx_content_flags_target (content_kind, content_id),
            INDEX idx_content_flags_reporter (reporter_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id           INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            church_id    INT UNSIGNED NULL,
            user_id      INT UNSIGNED NOT NULL,
            actor_id     INT UNSIGNED NULL,
            type         VARCHAR(32) NOT NULL,
            target_kind  VARCHAR(32) NULL,
            target_id    INT UNSIGNED NULL,
            url          VARCHAR(500) NULL,
            body         VARCHAR(280) NULL,
            read_at      DATETIME NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_notifications_user (user_id, read_at, created_at),
            INDEX idx_notifications_target (target_kind, target_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
