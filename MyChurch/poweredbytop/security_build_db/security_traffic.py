# ================================================================
# poweredbytop/security_build_db/security_traffic.py
# Table Builder: pbt_traffic (MariaDB)
# ROBUST, FUTURE-PROOF SCHEMA
# 100% FRESH - MARIADB ONLY
# ================================================================
# MARIADB ONLY - NO INSTANCE FOLDER - NO SQLITE - NO JSON
# ================================================================

def create_tables(cursor):
    """Create the pbt_traffic table with robust future-proof schema"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pbt_traffic (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ip VARCHAR(45) NOT NULL,
            domain VARCHAR(255),
            vetted_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_ip_domain (ip, domain)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Indexes for fast lookups - robust
    for idx in [
        "CREATE INDEX idx_pbt_trf_ip_domain ON pbt_traffic(ip, domain)",
        "CREATE INDEX idx_pbt_trf_expires ON pbt_traffic(expires_at)",
    ]:
        try:
            cursor.execute(idx)
        except Exception:
            pass

    print("Table created/verified: pbt_traffic (MariaDB, robust schema)")