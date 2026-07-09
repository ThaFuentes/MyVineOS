# myvinechurchonline/app/models/db.py
# Full path: myvinechurchonline/app/models/db.py
# File name: db.py
# Brief, detailed purpose: MariaDB connection handler using PyMySQL.
# Provides a per-request connection with DictCursor (returns dict-like rows, matching previous sqlite3.Row behavior).
# Configuration is read from app.config keys:
#   MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
#   MYSQL_PORT (optional, defaults to 3306)
# Designed to be a near-drop-in replacement for the previous SQLite version while fully supporting MariaDB in Docker.

from flask import current_app, g
import pymysql

def get_db():
    """
    Return the MariaDB connection for the current request.
    Creates it once per request and stores on flask.g for reuse.
    """
    if 'db' not in g:
        g.db = pymysql.connect(
            host=current_app.config['MYSQL_HOST'],
            user=current_app.config['MYSQL_USER'],
            password=current_app.config['MYSQL_PASSWORD'],
            database=current_app.config['MYSQL_DATABASE'],
            port=current_app.config.get('MYSQL_PORT', 3306),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
    return g.db


# Alias preserved for backward compatibility with any older imports
def get_db_connection():
    return get_db()


def close_db(e=None):
    """
    Close the database connection at the end of the request.
    Registered via app.teardown_appcontext in __init__.py.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db_command(app):
    """
    Helper to register teardown with the application instance.
    Call this inside your create_app() factory.
    """
    app.teardown_appcontext(close_db)