# app/routes/inventory/utils.py
# Full path: MyVineChurch/app/routes/inventory/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Inventory module.
# - REQUIRED_ROLES constant
# - current_user_id() helper for logging and ownership
# - UPC lookup URL constant
# - Barcode lookup fallback logic
# - Stock calculation helpers (low stock, expiring soon)
# - Designed for easy future growth (stock calculations, alerts, reports, etc.).
# - 100% matches the original inventory.py helpers and constants.

from flask import session
import requests
from datetime import datetime, timedelta

from app.utils.permissions import user_has_permission


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']


def can_manage_inventory() -> bool:
    return user_has_permission('manage_inventory')
UPCITEMDB_TRIAL_URL = "https://api.upcitemdb.com/prod/trial/lookup"


# ----------------------------------------------------------------------
# User Helpers
# ----------------------------------------------------------------------
def current_user_id():
    """Return current logged-in user ID for logging and ownership."""
    return session.get('user_id')


# ----------------------------------------------------------------------
# Barcode Lookup Helper
# ----------------------------------------------------------------------
def external_barcode_lookup(code):
    """Fallback external UPC lookup using UPCItemDB trial API."""
    try:
        resp = requests.get(f"{UPCITEMDB_TRIAL_URL}?upc={code}", timeout=5)
        data = resp.json()
        if data.get('code') == 'OK' and data.get('items'):
            prod = data['items'][0]
            return {
                'source': 'external',
                'title': prod.get('title', ''),
                'brand': prod.get('brand', ''),
                'description': prod.get('description', ''),
                'images': prod.get('images', []),
                'category': prod.get('category', ''),
                'upc': code
            }
    except Exception as e:
        print(f"External UPC lookup error: {e}")
    return None


# ----------------------------------------------------------------------
# Stock Helpers
# ----------------------------------------------------------------------
def is_low_stock(current_stock, min_stock_level):
    """Helper to determine if an item is low stock."""
    if min_stock_level is None:
        return False
    return current_stock < min_stock_level


def is_expiring_soon(expiration_date, days=30):
    """Check if item is expiring soon."""
    if not expiration_date:
        return False
    try:
        expire_date = datetime.strptime(expiration_date, '%Y-%m-%d')
        return expire_date <= (datetime.now() + timedelta(days=days))
    except Exception:
        return False