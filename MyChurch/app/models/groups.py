# myvinechurchonline/app/models/groups.py
# Full path: myvinechurchonline/app/models/groups.py
# File name: groups.py
# Brief, detailed purpose: Provides centralized query and manipulation functions for groups and user-group assignments in MariaDB.
# Includes creation, retrieval, updating, soft-deletion of groups; user assignment/removal; membership checks.
# Integrates with audit logging via log_change for all mutations. Handles errors gracefully.
# Permissions stored/parsing as JSON in TEXT column. Supports role_in_group and joined_at tracking.
# Used across routes for group management without duplicating SQL. Layered additively on core auth.

import json
from typing import List, Dict, Optional, Any
from app.models.db import get_db
from app.models.log import log_change
from pymysql.err import IntegrityError


def create_group(
        name: str,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, Any]] = None,
        created_by: int = 1,  # Default to Owner ID; override with session user
        is_active: int = 1
) -> int:
    """
    Create a new group and return its ID. Logs the action.
    Permissions stored as JSON string.
    """
    db = get_db()
    cur = db.cursor()
    permissions_json = json.dumps(permissions or {})
    try:
        cur.execute("""
            INSERT INTO groups (name, description, permissions, is_active, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, description, permissions_json, is_active, created_by, created_by))
        group_id = cur.lastrowid
        log_change(
            user_id=created_by,
            action='create_group',
            target_table='groups',
            target_id=group_id,
            details=f"Created group '{name}' with description '{description}'."
        )
        return group_id
    except IntegrityError as e:
        raise ValueError(f"Group creation failed: Name '{name}' already exists.") from e


def get_group_by_id(group_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a group by ID, with permissions parsed from JSON.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM groups WHERE id = %s", (group_id,))
    group = cur.fetchone()
    if group:
        group_dict = dict(group)
        group_dict['permissions'] = json.loads(group_dict['permissions'])
        return group_dict
    return None


def get_all_groups(active_only: bool = True) -> List[Dict[str, Any]]:
    """
    Retrieve all groups, optionally filtered to active ones. Permissions parsed.
    """
    db = get_db()
    cur = db.cursor()
    if active_only:
        cur.execute("SELECT * FROM groups WHERE is_active = 1 ORDER BY name")
    else:
        cur.execute("SELECT * FROM groups ORDER BY name")
    groups = cur.fetchall()
    return [
        {**dict(g), 'permissions': json.loads(g['permissions'])} for g in groups
    ]


def update_group(
        group_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[Dict[str, Any]] = None,
        is_active: Optional[int] = None,
        updated_by: int = 1
) -> None:
    """
    Update a group's details. Only provided fields are updated. Logs the action.
    """
    db = get_db()
    cur = db.cursor()
    updates = []
    params = []
    details = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
        details.append(f"name to '{name}'")
    if description is not None:
        updates.append('description = %s')
        params.append(description)
        details.append(f"description to '{description}'")
    if permissions is not None:
        updates.append('permissions = %s')
        params.append(json.dumps(permissions))
        details.append("permissions updated")
    if is_active is not None:
        updates.append('is_active = %s')
        params.append(is_active)
        details.append(f"is_active to {is_active}")

    if updates:
        updates.append('updated_at = CURRENT_TIMESTAMP')
        updates.append('updated_by = %s')
        params.append(updated_by)
        params.append(group_id)

        query = f"UPDATE groups SET {', '.join(updates)} WHERE id = %s"
        cur.execute(query, params)
        log_change(
            user_id=updated_by,
            action='update_group',
            target_table='groups',
            target_id=group_id,
            details=f"Updated group ID {group_id}: {', '.join(details)}."
        )


def delete_group(group_id: int, deleted_by: int = 1) -> None:
    """
    Soft-delete a group by setting is_active=0. Logs the action.
    """
    update_group(group_id, is_active=0, updated_by=deleted_by)
    log_change(
        user_id=deleted_by,
        action='delete_group',
        target_table='groups',
        target_id=group_id,
        details=f"Soft-deleted group ID {group_id}."
    )


def assign_user_to_group(
        user_id: int,
        group_id: int,
        role_in_group: str = 'member',
        assigned_by: int = 1
) -> None:
    """
    Assign a user to a group with optional role. Logs the action.
    """
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
            VALUES (%s, %s, %s, %s)
        """, (user_id, group_id, role_in_group, assigned_by))
        log_change(
            user_id=assigned_by,
            action='assign_user_to_group',
            target_table='user_groups',
            target_id=cur.lastrowid,
            details=f"Assigned user ID {user_id} to group ID {group_id} as '{role_in_group}'."
        )
    except IntegrityError as e:
        raise ValueError(f"Assignment failed: User {user_id} already in group {group_id}.") from e


def remove_user_from_group(user_id: int, group_id: int, removed_by: int = 1) -> None:
    """
    Remove a user from a group. Logs the action.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        DELETE FROM user_groups
        WHERE user_id = %s AND group_id = %s
    """, (user_id, group_id))
    if cur.rowcount > 0:
        log_change(
            user_id=removed_by,
            action='remove_user_from_group',
            target_table='user_groups',
            details=f"Removed user ID {user_id} from group ID {group_id}."
        )


def get_user_groups(user_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all active groups a user belongs to, with role_in_group and joined_at.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT g.*, ug.role_in_group, ug.joined_at
        FROM groups g
        JOIN user_groups ug ON g.id = ug.group_id
        WHERE ug.user_id = %s
          AND g.is_active = 1
        ORDER BY g.name
    """, (user_id,))
    groups = cur.fetchall()
    return [
        {**dict(g), 'permissions': json.loads(g['permissions'])} for g in groups
    ]


def check_user_in_group(user_id: int, group_name: str) -> bool:
    """
    Check if a user is in a specific active group (by name; case-sensitive).
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 1
        FROM user_groups ug
        JOIN groups g ON ug.group_id = g.id
        WHERE ug.user_id = %s
          AND g.name = %s
          AND g.is_active = 1
    """, (user_id, group_name))
    return cur.fetchone() is not None


def get_group_members(group_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all members of a group, with their roles.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.first_name, u.last_name, ug.role_in_group
        FROM users u
        JOIN user_groups ug ON u.id = ug.user_id
        WHERE ug.group_id = %s
        ORDER BY u.last_name, u.first_name
    """, (group_id,))
    return [dict(m) for m in cur.fetchall()]