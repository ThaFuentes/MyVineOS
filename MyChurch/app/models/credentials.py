# app/models/credentials.py
# Full path: MyVineChurch/app/models/credentials.py
# File name: credentials.py
# Brief, detailed purpose: Centralized secure encryption for bill credentials.
# Auto-generates and saves FERNET_KEY to .env if missing (development friendly).

from flask import current_app
from cryptography.fernet import Fernet, InvalidToken
import os

def _valid_fernet_key(key):
    if not key:
        return False
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
        return True
    except (ValueError, TypeError):
        return False


def get_fernet():
    """Returns Fernet instance. Auto-creates and saves key to .env if missing or invalid."""
    key = current_app.config.get('FERNET_KEY')

    if not _valid_fernet_key(key):
        key = Fernet.generate_key().decode()
        print("\n" + "="*80)
        print("FERNET_KEY was missing or invalid -> Generated a new secure key:")
        print(key)
        print("This key has been automatically saved to your .env file.")
        print("Keep this key safe - losing it will make all saved credentials unreadable!")
        print("="*80 + "\n")

        # Save to .env automatically
        env_path = os.path.join(os.path.dirname(current_app.root_path), '.env')
        try:
            with open(env_path, 'a') as f:
                f.write(f"\nFERNET_KEY={key}\n")
        except Exception as e:
            print(f"Warning: Could not write to .env: {e}")

        current_app.config['FERNET_KEY'] = key

    return Fernet(key)


def encrypt_credential(text: str):
    """Encrypt string. Returns bytes or None if empty."""
    if not text:
        return None
    fernet = get_fernet()
    return fernet.encrypt(text.encode())


def decrypt_credential(encrypted_bytes):
    """Decrypt bytes. Returns string or '[Decryption failed]'."""
    if not encrypted_bytes:
        return ''
    try:
        fernet = get_fernet()
        return fernet.decrypt(encrypted_bytes).decode()
    except (InvalidToken, Exception):
        return '[Decryption failed - wrong key or corrupted data]'