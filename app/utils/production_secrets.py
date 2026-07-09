# app/utils/production_secrets.py
# Refuse insecure default secrets when running in production mode.

import os

_INSECURE_SECRET_KEY_MARKERS = (
    'dev-insecure',
    'change-this',
    'changeme',
)

_INSECURE_PBT_TOKEN_MARKERS = (
    'CHANGE-THIS',
    'changeme',
)


def _is_production() -> bool:
    return (
        os.getenv('FLASK_ENV') == 'production'
        or os.getenv('REQUIRE_HTTPS', '').lower() in ('1', 'true', 'yes')
    )


def _looks_insecure(value: str | None, markers: tuple[str, ...]) -> bool:
    if not value or not str(value).strip():
        return True
    lower = str(value).lower()
    return any(m.lower() in lower for m in markers)


def validate_production_secrets() -> None:
    """Raise on startup if production is configured with known-weak secrets."""
    if not _is_production():
        return

    problems = []
    secret_key = os.environ.get('SECRET_KEY', '')
    if _looks_insecure(secret_key, _INSECURE_SECRET_KEY_MARKERS):
        problems.append('SECRET_KEY must be set to a long random value in production')

    fernet = os.environ.get('FERNET_KEY', '')
    if not fernet or len(fernet) < 32:
        problems.append('FERNET_KEY must be set (32+ char Fernet key) in production')

    pbt_token = os.environ.get('PBT_TOKEN_SECRET', '')
    if _looks_insecure(pbt_token, _INSECURE_PBT_TOKEN_MARKERS):
        problems.append('PBT_TOKEN_SECRET must be set to a long random value in production')

    if problems:
        raise RuntimeError(
            'Insecure production configuration: ' + '; '.join(problems)
        )