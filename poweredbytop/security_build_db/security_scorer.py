# ================================================================
# poweredbytop/security_build_db/security_scorer.py
# Table Builder: pbt_reputation (MariaDB)
# ROBUST, FUTURE-PROOF SCHEMA
# 100% FRESH - MARIADB ONLY
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================

def create_tables(cursor):
    """Create the pbt_reputation table (core for scorer.py)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pbt_reputation (
            ip VARCHAR(45) PRIMARY KEY,
            score INT DEFAULT 100,
            grade VARCHAR(20) DEFAULT 'normal',
            positive_requests INT DEFAULT 0,
            negative_points INT DEFAULT 0,
            ban_until DATETIME NULL,
            ban_reason TEXT NULL,
            ban_count INT DEFAULT 0,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_bad_behavior DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Safe index creation (compatible with older MariaDB)
    for idx_sql in [
        "CREATE INDEX idx_pbt_rep_ip ON pbt_reputation(ip)",
        "CREATE INDEX idx_pbt_rep_grade ON pbt_reputation(grade)",
        "CREATE INDEX idx_pbt_rep_last_seen ON pbt_reputation(last_seen)",
        "CREATE INDEX idx_pbt_rep_ban_until ON pbt_reputation(ban_until)",
    ]:
        try:
            cursor.execute(idx_sql)
        except Exception:
            pass  # index exists or other non-fatal

    print("Table created/verified: pbt_reputation (MariaDB)")