# ================================================================
# poweredbytop/security_build_db/security_stats.py
# Table Builder: pbt_attack_stats (MariaDB)
# ROBUST, FUTURE-PROOF SCHEMA
# 100% FRESH - MARIADB ONLY
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================

def create_tables(cursor):
    """Create the pbt_attack_stats table with robust future-proof schema"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pbt_attack_stats (
            attack_type VARCHAR(50) PRIMARY KEY,
            encrypted_count BLOB NOT NULL,
            total_attempts INT DEFAULT 0,
            blocked_count INT DEFAULT 0,
            last_attack_ip VARCHAR(45),
            last_attack_time DATETIME,
            severity_level INT DEFAULT 1,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Indexes for fast lookups - robust
    for idx in [
        "CREATE INDEX idx_pbt_ast_type ON pbt_attack_stats(attack_type)",
        "CREATE INDEX idx_pbt_ast_severity ON pbt_attack_stats(severity_level)",
        "CREATE INDEX idx_pbt_ast_last_attack ON pbt_attack_stats(last_attack_time)",
    ]:
        try:
            cursor.execute(idx)
        except Exception:
            pass

    print("Table created/verified: pbt_attack_stats (MariaDB, robust schema)")