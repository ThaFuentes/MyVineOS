# Purpose-bound Fernet for direct messages. Never reuse field_crypto.encrypt.

import os
from cryptography.fernet import Fernet

_key_path = os.path.join(os.path.dirname(__file__), '..', '..', 'dm_key.bin')
_env_key = os.environ.get('ENCRYPTION_KEY_DM')
if _env_key:
    _key = _env_key.encode() if isinstance(_env_key, str) else _env_key
elif os.path.exists(_key_path):
    with open(_key_path, 'rb') as f:
        _key = f.read().strip()
else:
    _key = Fernet.generate_key()
    with open(_key_path, 'wb') as f:
        f.write(_key)

_cipher = Fernet(_key)


def encrypt_dm(text: str) -> str:
    return _cipher.encrypt((text or '').encode()).decode() if text else ''


def decrypt_dm(token: str) -> str:
    if not token:
        return ''
    try:
        return _cipher.decrypt(token.encode()).decode()
    except Exception:
        return ''
