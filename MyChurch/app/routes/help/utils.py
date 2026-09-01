from app.utils.permissions import user_has_permission


def can_manage_help() -> bool:
    return user_has_permission('manage_help')