# ================================================================
# poweredbytop/security_build_db/security_events.py
# Table Builder: pbt_security_events (MariaDB)
# ROBUST, FUTURE-PROOF SCHEMA
# 100% FRESH - MARIADB ONLY
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================

def create_tables(cursor):
    """Create the pbt_security_events table with robust future-proof schema"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pbt_security_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type VARCHAR(50) NOT NULL,
            ip VARCHAR(45) NOT NULL,
            reputation_score INT DEFAULT 100,
            behavior_grade VARCHAR(20) DEFAULT 'normal',
            check_frequency INT DEFAULT 1,
            ban_until DATETIME NULL,
            ban_reason TEXT NULL,
            ban_count INT DEFAULT 0,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            encrypted_data BLOB,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Performance indexes - robust (try/except for existing)
    for idx in [
        "CREATE INDEX idx_pbt_evt_ip ON pbt_security_events(ip)",
        "CREATE INDEX idx_pbt_evt_grade ON pbt_security_events(behavior_grade)",
        "CREATE INDEX idx_pbt_evt_ban_until ON pbt_security_events(ban_until)",
        "CREATE INDEX idx_pbt_evt_last_seen ON pbt_security_events(last_seen)",
        "CREATE INDEX idx_pbt_evt_ip_grade ON pbt_security_events(ip, behavior_grade)",
    ]:
        try:
            cursor.execute(idx)
        except Exception:
            pass

    print("Table created/verified: pbt_security_events (MariaDB, robust schema)")