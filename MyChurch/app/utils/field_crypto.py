# Fernet encryption for stored credentials (email passwords, usernames, etc.)

import os
from cryptography.fernet import Fernet

_key_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config_key.bin')
_env_key = os.environ.get('ENCRYPTION_KEY')
if _env_key:
    _key = _env_key.encode()
elif os.path.exists(_key_path):
    with open(_key_path, 'rb') as f:
        _key = f.read()
else:
    _key = Fernet.generate_key()
    with open(_key_path, 'wb') as f:
        f.write(_key)

_cipher = Fernet(_key)


def encrypt(text: str) -> str:
    return _cipher.encrypt(text.encode()).decode() if text else ''


def decrypt(token: str) -> str:
    if not token:
        return ''
    try:
        return _cipher.decrypt(token.encode()).decode()
    except Exception:
        return ''