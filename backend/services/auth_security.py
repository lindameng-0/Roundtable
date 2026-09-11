"""Password hashing and opaque authentication-token helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address")
    return email


def validate_password(value: str) -> str:
    password = value or ""
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(password) > 128:
        raise ValueError("Password must be 128 characters or fewer")
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one letter and one number")
    return password


def hash_password(password: str) -> str:
    password = validate_password(password)
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N,
        SCRYPT_R,
        SCRYPT_P,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def new_opaque_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_opaque_token(raw)


def hash_opaque_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()
