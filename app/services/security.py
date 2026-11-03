"""Password hashing, opaque API tokens, IP hashing. Standard library only."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


_DUMMY = hash_password("not-a-real-password")


def burn_password_check(password: str) -> None:
    """Equalise timing when the email is unknown."""
    verify_password(password, _DUMMY)


def new_token() -> tuple[str, str]:
    """Returns (plaintext token shown once, sha256 stored in DB)."""
    raw = "fw_" + secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_ip(ip: str, secret: str) -> str:
    """Keyed hash - we never store raw visitor IPs."""
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()


def new_id(nbytes: int = 12) -> str:
    return secrets.token_hex(nbytes)
