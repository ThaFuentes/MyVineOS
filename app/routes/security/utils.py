# Access control for the Security console.

from flask import session

from app.utils.permissions import user_has_permission
from app.models.db import get_db
import pymysql

SECURITY_PERM = 'manage_security'
# Roles that always see the console (and can manage name grants for Admin/Owner)
ALWAYS_ROLES = frozenset(['Owner', 'Admin', 'Staff'])
GRANT_MANAGER_ROLES = frozenset(['Owner', 'Admin'])


def ensure_security_grants_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS security_area_grants (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNSIGNED NOT NULL,
            granted_by INT UNSIGNED NULL,
            notes VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_security_grant_user (user_id),
            CONSTRAINT fk_sec_grant_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_sec_grant_by FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    try:
        db.commit()
    except Exception:
        pass


def has_named_security_grant(user_id: int | None) -> bool:
    if not user_id:
        return False
    try:
        ensure_security_grants_table()
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            "SELECT 1 AS ok FROM security_area_grants WHERE user_id = %s LIMIT 1",
            (user_id,),
        )
        return bool(cur.fetchone())
    except Exception as exc:
        print(f'security grant check: {exc}')
        return False


def can_access_security_console(user_id: int | None = None, role: str | None = None) -> bool:
    """Owner/Admin/Staff, manage_security permission, or explicit name grant."""
    uid = user_id if user_id is not None else session.get('user_id')
    role = role if role is not None else session.get('user_role')
    if not uid:
        return False
    if role in ALWAYS_ROLES:
        return True
    if user_has_permission(SECURITY_PERM):
        return True
    return has_named_security_grant(uid)


def can_manage_security_access(role: str | None = None) -> bool:
    """Only Owner/Admin may add/remove named access grants."""
    role = role if role is not None else session.get('user_role')
    return role in GRANT_MANAGER_ROLES
