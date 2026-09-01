# app/routes/events/event_contributions.py
# Full path: MyVineChurch/app/routes/events/event_contributions.py
# File name: event_contributions.py
# Brief, detailed purpose: Contains only the potluck contribution deletion route.
# Restricted to Admin/Owner only. Deletes a single signup row.
# Logs the deletion and flashes success/error. Redirects back to the event detail view.
# No other routes or logic - pure extraction from the original monolithic events.py.

from flask import redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.models.db import get_db
from app.models.log import log_change

ADMIN_OWNER_ONLY = ['Admin', 'Owner']

def register_contributions_routes(bp):
    @bp.route('/<int:event_id>/delete_contribution/<int:signup_id>', methods=['POST'])
    @login_required
    @role_required(ADMIN_OWNER_ONLY)
    def delete_contribution(event_id, signup_id):
        db = get_db()
        cur = db.cursor()

        try:
            cur.execute("""
                DELETE FROM potluck_signups
                WHERE id = %s AND event_id = %s
            """, (signup_id, event_id))
            db.commit()

            if cur.rowcount:
                log_change(
                    session['user_id'],
                    'delete_potluck_contribution',
                    target_id=event_id,
                    change_details=f"Deleted potluck signup ID {signup_id}"
                )
                flash('Contribution removed.', 'success')
            else:
                flash('Contribution not found.', 'error')
        except Exception:
            db.rollback()
            flash('Failed to delete contribution.', 'error')

        return redirect(url_for('events.view_event', event_id=event_id))