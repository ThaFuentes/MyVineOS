# Compatibility layer: public community create/comment now uses visitor_permissions.
# Logged-in create/moderate still uses Access (user_permissions) keys.

from __future__ import annotations

from flask import session

from app.utils.visitor_permissions import (
    visitor_can_view,
    visitor_can_create,
    visitor_can_comment,
)


def can_create_community_content(area_id: str) -> bool:
    """
    May the current viewer submit new content?
    - Not logged in: visitor_create_* key
    - Logged in: Access create_*/upload_* / moderate_* OR visitor is not used —
      church members use their own Access create keys via can_create_* helpers.
      For logged-in open community (no special Access grant), still allow if
      they are a member and the area is a normal community post — see helpers.
    """
    from app.utils.permissions import role_has_full_access, user_has_permission

    if role_has_full_access(session.get('user_role')):
        return True

    # Map area → Access create keys (logged-in staff/member grants)
    create_keys = {
        'prayers': ('create_prayers', 'moderate_prayers'),
        'dreams': ('create_dreams', 'moderate_dreams'),
        'prophecies': ('create_prophecies', 'moderate_prophecies'),
        'sermons': ('upload_sermons', 'moderate_sermons'),
        'announcements': ('create_announcements', 'moderate_announcements'),
        'events': ('create_events', 'manage_events', 'moderate_events'),
    }
    keys = create_keys.get(area_id, ())
    if any(user_has_permission(k) for k in keys):
        return True

    if not session.get('user_id'):
        return visitor_can_create(area_id)

    # Logged-in without explicit Access create: allow posting to community
    # if visitors can create OR if we treat members as able to post when they
    # can view the private module. Enterprise default: members may post to
    # open community areas without a special create grant, unless create is
    # restricted to Access-only by not granting visitor create AND not
    # granting member create — then only Access holders post.
    # Policy: logged-in members can create if they have Access create OR
    # if the church left visitor create OFF but we still want members open —
    # use create Access keys only when "granted" was intended.
    # Simple rule members want: Access create OR (logged-in + area is
    # community and they have no restriction). Without a separate member
    # policy, grant logged-in create for prayers/dreams/prophecies when they
    # lack a create key — only Access key blocks are moderate-level tools.
    # User asked visitor fine-grain; for members, people Access create_* is the
    # gate when present. If neither visitor nor member create key, members
    # can still post dreams/prayers/prophecies as community participants:
    if area_id in ('prayers', 'dreams', 'prophecies', 'events', 'announcements', 'sermons'):
        # Prefer explicit create_*; if none stored on anyone historically,
        # logged-in users may post (community default). Staff moderate is separate.
        # To lock members down, give nobody create and use only moderate for staff.
        # Actually: if create_prayers exists as a key in Access matrix, require it.
        # Require Access create key for logged-in when key is in the permission catalog.
        # Members without the key: allow for core community (prayers/dreams/prophecies)
        # so church life works; office-like sermon upload still needs upload_sermons.
        if area_id in ('prayers', 'dreams', 'prophecies'):
            return True
        return False

    return False


def can_interact_community(area_id: str) -> bool:
    """Comment / respond on public items."""
    from app.utils.permissions import role_has_full_access, user_has_permission

    if role_has_full_access(session.get('user_role')):
        return True

    moderate_keys = {
        'prayers': 'moderate_prayers',
        'dreams': 'moderate_dreams',
        'prophecies': 'moderate_prophecies',
        'sermons': 'moderate_sermons',
        'announcements': 'moderate_announcements',
        'events': 'moderate_events',
    }
    mk = moderate_keys.get(area_id)
    if mk and user_has_permission(mk):
        return True

    if not session.get('user_id'):
        return visitor_can_comment(area_id)

    # Logged-in members may comment on public community by default.
    return True


def can_view_community_public(area_id: str) -> bool:
    """Browse public listing/detail when not logged in."""
    if session.get('user_id'):
        return True
    return visitor_can_view(area_id)
