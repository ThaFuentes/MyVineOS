# app/models/old_settings.py
# Full path: myvinechurchonline/app/models/old_settings.py
# File name: old_settings.py
# Brief, detailed purpose: Loads church-wide settings from the single-row 'settings' table.
# Returns a dict with safe defaults if no row exists or query fails.
# Used globally via before_request to populate g.settings.
# Now includes online giving page controls added in recent migration.

from app.models.db import get_db
import pymysql

def get_settings():
    """
    Fetch the settings row (assumes single row in table).
    Returns dict with values or defaults on failure/missing row.
    """
    defaults = {
        'church_name': None,
        'primary_color': '#00FFFF',
        'primary_hover_color': '#00cccc',
        'font_family': 'system-ui, -apple-system, sans-serif',
        'background_opacity': 0.68,
        'favicon_path': None,
        'logo_path': None,
        'background_image': None,
        # Existing branding / paths – add new ones here as created in DB

        # ----- NEW ONLINE GIVING GLOBAL SETTINGS -----
        'online_donations_enabled': 0,                                      # 0 = Donate tab hidden from public nav
        'donations_page_title': 'Support Our Ministry',
        'donations_welcome_text': 'Thank you for considering a gift to support our ministry.',
        'donations_thank_you_text': 'Thank you for your generous support!',
        'donations_extra_text': None                                        # Optional additional content (can be NULL)
    }

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT * FROM settings LIMIT 1")
        row = cur.fetchone()
        if row:
            # Merge DB values with defaults (DB overrides defaults)
            defaults.update(row)
            return defaults
    except Exception as e:
        print(f"Settings load error: {e}")

    return defaults