# myvinechurchonline/app/config.py
# Full path: myvinechurchonline/app/config.py
# File name: config.py
# Brief, detailed purpose: Configuration classes for the Flask application in MariaDB environment.
# Defines base Config and environment-specific subclasses (DevelopmentConfig, ProductionConfig, TestingConfig).
# All database settings use MYSQL_* environment variables (standard for Docker/MariaDB).
# Sensitive values (SECRET_KEY, MYSQL_PASSWORD) must come from environment in production.
# Upload/export paths remain relative to project root for consistency.
# Email settings are placeholders — actual encrypted credentials stored in settings table.

import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration class — shared defaults."""
    # General
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-insecure-default-immediately-2026'
    DEBUG = False
    TESTING = False

    # MariaDB (Docker/production-ready)
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'churchuser')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'church_management')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))

    # Uploads (persistent storage)
    UPLOAD_FOLDER = os.path.join(basedir, '..', 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'mp3', 'mp4', 'jpg', 'jpeg', 'png', 'docx', 'txt', 'wav'}

    # Exports (generated reports)
    EXPORT_FOLDER = os.path.join(basedir, '..', 'export')

    # Max upload size (16 MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Email placeholders (actual encrypted values stored in settings table)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.example.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


class DevelopmentConfig(Config):
    """Development-specific configuration."""
    DEBUG = True
    # Use local defaults for convenience; override with env vars as needed
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'devpassword')  # Insecure default for dev only


class ProductionConfig(Config):
    """Production-specific configuration."""
    DEBUG = False
    # Force sensitive values from environment only
    SECRET_KEY = os.environ.get('SECRET_KEY')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
    if not SECRET_KEY or not MYSQL_PASSWORD:
        raise RuntimeError("SECRET_KEY and MYSQL_PASSWORD must be set in production environment.")


class TestingConfig(Config):
    """Testing-specific configuration."""
    TESTING = True
    DEBUG = True
    # Use a separate test database to avoid polluting dev/prod data
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'church_management_test')
    # Optional: weaker secrets for CI
    SECRET_KEY = 'test-secret-key'