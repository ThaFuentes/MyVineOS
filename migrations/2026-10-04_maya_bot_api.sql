-- My Vine Church: Maya bot API (/api/bot/maya/*) + Owner checklist (/settings/maya-permissions)
-- 2026-10-04. MariaDB. Idempotent. The app also creates these lazily
-- (app/utils/maya_perms.py ensure_tables), so running this is optional.

CREATE TABLE IF NOT EXISTS maya_bot_settings (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  key_id INT NOT NULL,                -- bot_access_keys.id designated as Maya
  acting_user_id INT NULL,            -- users.id her writes are attributed to (NULL = key creator)
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  set_by INT NULL,
  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS maya_bot_permissions (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  key_id INT NOT NULL,
  perm VARCHAR(64) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  expires_at DATETIME NULL,           -- auto-off time (UTC). NULL = no expiry. High risk always has one.
  updated_by INT NULL,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_maya_perm (key_id, perm),
  KEY idx_maya_perm_expiry (enabled, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE maya_bot_permissions ADD COLUMN IF NOT EXISTS expires_at DATETIME NULL AFTER enabled;

CREATE TABLE IF NOT EXISTS maya_bot_perm_log (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  key_id INT NULL,
  changed_by INT NULL,                -- Owner user id; NULL for auto-expired
  perm VARCHAR(64) NOT NULL,
  old_value TINYINT(1) NULL,
  new_value TINYINT(1) NULL,
  high_risk TINYINT(1) NOT NULL DEFAULT 0,
  confirmed_with VARCHAR(16) NULL,    -- password | totp | ...,timer | auto-expired
  ip VARCHAR(64) NULL,
  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_maya_perm_log_when (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Designate Maya = first active bot key named like 'maya' (only if none chosen yet).
-- Permission rows need no seed: missing row = default (normal ON, high risk OFF).
INSERT INTO maya_bot_settings (key_id, acting_user_id, enabled)
SELECT k.id, k.created_by, 1 FROM bot_access_keys k
WHERE k.active = 1 AND LOWER(k.name) LIKE '%maya%'
  AND NOT EXISTS (SELECT 1 FROM maya_bot_settings)
ORDER BY k.id ASC LIMIT 1;
