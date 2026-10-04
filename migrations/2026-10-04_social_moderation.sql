-- MyVineChurch social moderation + notifications (2026-10-04)
-- Additive and safe to run more than once. The app also creates these on
-- startup through app/builddb/social_moderation.py (build_all), so running
-- this by hand is optional; do it before the restart if you want it explicit.
--
-- Soft deletes reuse columns the app already has:
--   community_posts.removed_at / removed_by        (wall posts)
--   <comment tables>.removed / moderated_by / moderated_at
--   prayers/dreams/prophecies/... .moderation_hidden (+ prayers.status='hidden')
-- and every delete/hide/restore is written to moderation_actions.

CREATE TABLE IF NOT EXISTS content_flags (
    id                   INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    church_id            INT UNSIGNED NULL,
    content_kind         VARCHAR(32) NOT NULL,
    content_id           INT UNSIGNED NULL,
    content_table        VARCHAR(64) NULL,
    author_id            INT UNSIGNED NULL,
    source               VARCHAR(16) NOT NULL DEFAULT 'report',   -- report | wordlist | ai
    category             VARCHAR(24) NOT NULL DEFAULT 'other',
    severity             TINYINT UNSIGNED NOT NULL DEFAULT 1,
    ai_score             DECIMAL(4,3) NULL,
    ai_reason            VARCHAR(500) NULL,
    reporter_id          INT UNSIGNED NULL,
    reporter_note        VARCHAR(500) NULL,
    excerpt              VARCHAR(500) NULL,                       -- masked; never the banned word
    context              VARCHAR(160) NULL,
    status               VARCHAR(16) NOT NULL DEFAULT 'open',     -- open | hidden | dismissed | restored | blocked
    resolved_by          INT UNSIGNED NULL,
    resolved_at          DATETIME NULL,
    moderation_action_id INT UNSIGNED NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_content_flags_report (content_kind, content_id, source, reporter_id),
    INDEX idx_content_flags_status (status, severity, created_at),
    INDEX idx_content_flags_target (content_kind, content_id),
    INDEX idx_content_flags_reporter (reporter_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS notifications (
    id           INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    church_id    INT UNSIGNED NULL,
    user_id      INT UNSIGNED NOT NULL,
    actor_id     INT UNSIGNED NULL,
    type         VARCHAR(32) NOT NULL,     -- reaction | praying | comment | reply | prayer_response | follow | mention | dm
    target_kind  VARCHAR(32) NULL,
    target_id    INT UNSIGNED NULL,
    url          VARCHAR(500) NULL,
    body         VARCHAR(280) NULL,
    read_at      DATETIME NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notifications_user (user_id, read_at, created_at),
    INDEX idx_notifications_target (target_kind, target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Existing installs: make sure the soft-delete columns the code relies on exist.
-- ADD COLUMN IF NOT EXISTS needs MariaDB 10.0.2+ (MySQL 8 lacks it; on MySQL skip
-- these lines -- the app adds missing columns itself on startup).
-- (build_all adds them too; these are no-ops when they are already there.)
ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS removed_at DATETIME NULL;
ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS removed_by INT UNSIGNED NULL;
ALTER TABLE prayers    ADD COLUMN IF NOT EXISTS moderation_hidden TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE dreams     ADD COLUMN IF NOT EXISTS moderation_hidden TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE prophecies ADD COLUMN IF NOT EXISTS moderation_hidden TINYINT(1) NOT NULL DEFAULT 0;
