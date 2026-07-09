# app/routes/donations/queries.py
# Full path: MyVineChurch/app/routes/donations/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Donations module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Wraps/re-exports every function from app.models.donation.py so the donations package is fully self-contained.
# - 100% original behavior preserved (dashboard data, add/edit/delete, reports, exports, member lists, etc.).
# - Designed for easy growth - we can move the actual SQL code here later if we want complete separation from models/.

from app.models.donation import (
    get_dashboard_data,
    add_donation,
    get_donation_by_id,
    update_donation,
    delete_donation,
    get_view_all_data,
    get_reports_data,
    get_export_years,
    get_members_with_donations,
    get_members_for_selector,
    get_member_for_export,
    get_donations_for_export,
    get_unique_donor_names
)

# ----------------------------------------------------------------------
# Clean re-exports (so views.py can import from .queries instead of deep models)
# ----------------------------------------------------------------------
__all__ = [
    'get_dashboard_data',
    'add_donation',
    'get_donation_by_id',
    'update_donation',
    'delete_donation',
    'get_view_all_data',
    'get_reports_data',
    'get_export_years',
    'get_members_with_donations',
    'get_members_for_selector',
    'get_member_for_export',
    'get_donations_for_export',
    'get_unique_donor_names'
]