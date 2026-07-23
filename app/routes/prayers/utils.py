# app/routes/prayers/utils.py
# Prayers: church participation policy + Access create/moderate.

from flask import session

from app.utils.community_participation import can_create_community_content
from app.utils.permissions import user_has_permission


REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']
ADMIN_ROLES = ['Admin', 'Owner']


def can_create_prayers() -> bool:
    return can_create_community_content('prayers')


def can_moderate_prayers() -> bool:
    return user_has_permission('moderate_prayers')


def is_admin_or_owner():
    return session.get('user_role') in ADMIN_ROLES


def is_staff_plus():
    return session.get('user_role') in REQUIRED_ROLES or can_moderate_prayers()


def get_default_visibility():
    return 'public'
