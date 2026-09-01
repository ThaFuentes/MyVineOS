# app/models/pastoral/__init__.py
# Full path: WebChurchMan/app/models/pastoral/__init__.py
# File name: __init__.py
# Brief, detailed purpose:
#   Sub-package initializer and public facade for all Pastoral Area model functions.
#   Re-exports EVERY function from the modular sub-files so existing code can continue
#   importing like this (during transition):
#       from app.models.pastoral import get_visible_sermons, is_in_pastoral_group, ...
#
#   Once all routes are updated to import directly from sub-modules (recommended long-term),
#   this file can be simplified or removed.

# Shared / cross-cutting helpers
from .shared import is_in_pastoral_group, get_pastoral_team_members, get_active_members_for_care

# Bible module
from .bible import (
    get_bible_translations,
    set_bible_default,
    delete_bible_translation,
    bible_search,
    bible_get_chapter
)

# Sermons module
from .sermons import (
    get_visible_sermons,
    get_sermon_by_id,
    create_sermon,
    update_sermon,
    delete_sermon,
    get_sermon_sections,
    save_sermon_sections,
    get_collaborators,
    add_collaborator,
    remove_collaborator
)

# Service Plans module
from .service_plans import (
    get_all_service_plans,
    get_service_plan_by_date,
    create_or_update_service_plan,
    get_service_plan_assignments,
    save_service_plan_assignments
)

# Illustrations module
from .illustrations import (
    get_visible_illustrations,
    get_illustration_by_id,
    create_illustration,
    update_illustration,
    delete_illustration
)

# Vault module
from .vault import (
    get_my_vault,
    get_shared_vault,
    add_vault_item,
    update_vault_item,
    delete_vault_item,
    search_vault_and_sermons
)

# Pastoral Care module
from .care import (
    fetch_care_requests,
    get_care_requests,
    get_care_request_by_id,
    create_care_request,
    update_care_request,
    delete_care_request,
    get_care_assignments,
    add_care_assignment,
    remove_care_assignment,
    get_care_notes,
    add_care_note
)