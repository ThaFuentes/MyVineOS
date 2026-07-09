# Optional TOTP two-factor authentication for users.

import pyotp
from app.utils.field_crypto import encrypt, decrypt


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, username: str, issuer: str = 'MyVine Church') -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp_code(secret_plain: str, code: str) -> bool:
    if not secret_plain or not code:
        return False
    code = str(code).strip().replace(' ', '')
    totp = pyotp.TOTP(secret_plain)
    return totp.verify(code, valid_window=1)


def encrypt_totp_secret(secret: str) -> str:
    return encrypt(secret)


def decrypt_totp_secret(encrypted: str) -> str:
    return decrypt(encrypted)