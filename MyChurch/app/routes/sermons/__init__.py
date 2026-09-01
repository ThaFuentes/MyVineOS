# app/routes/sermons/__init__.py
# Full path: WebChurchMan/app/routes/sermons/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Package initializer for the sermons blueprint.
# Imports and exposes sermons_bp from views.py so it can be registered in the main app factory (app/__init__.py).
# Follows the exact modularization standard used across all features (dreams, events, tickets, etc.).

from .views import sermons_bp

__all__ = ['sermons_bp']