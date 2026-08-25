"""Shared credential primitives for purpose-scoped local access gates."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from typing import Final

ACCESS_CODE_SEGMENT_LENGTH: Final = 4
ACCESS_CODE_SEGMENT_COUNT: Final = 2
ACCESS_CODE_SALT_BYTES: Final = 16
ACCESS_CODE_HASH_BYTES: Final = 32
ACCESS_TOKEN_BYTES: Final = 32
ACCESS_TOKEN_HASH_BYTES: Final = 32
PBKDF2_SHA256_ITERATIONS: Final = 210_000

_ACCESS_CODE_ALPHABET: Final = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"


def generate_access_code() -> str:
    """Return a human-readable code without ambiguous characters."""

    return "-".join(
        "".join(secrets.choice(_ACCESS_CODE_ALPHABET) for _ in range(ACCESS_CODE_SEGMENT_LENGTH))
        for _ in range(ACCESS_CODE_SEGMENT_COUNT)
    )


def generate_code_salt() -> bytes:
    return secrets.token_bytes(ACCESS_CODE_SALT_BYTES)


def normalize_access_code(code: str) -> str:
    return code.strip().upper()


def hash_access_code(code: str, salt: bytes) -> bytes:
    """Derive the stable PBKDF2 hash used by both access-session families."""

    return hashlib.pbkdf2_hmac(
        "sha256",
        normalize_access_code(code).encode("ascii", errors="ignore"),
        salt,
        PBKDF2_SHA256_ITERATIONS,
    )


def verify_access_code(code: str, *, salt: bytes, expected_hash: bytes) -> bool:
    return hmac.compare_digest(expected_hash, hash_access_code(code, salt))


def generate_access_token() -> str:
    return secrets.token_urlsafe(ACCESS_TOKEN_BYTES)


def hash_access_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii", errors="ignore")).digest()


def verify_access_token(token: str, *, expected_hash: bytes) -> bool:
    return hmac.compare_digest(expected_hash, hash_access_token(token))


__all__ = [
    "ACCESS_CODE_HASH_BYTES",
    "ACCESS_CODE_SALT_BYTES",
    "ACCESS_TOKEN_HASH_BYTES",
    "PBKDF2_SHA256_ITERATIONS",
    "generate_access_code",
    "generate_access_token",
    "generate_code_salt",
    "hash_access_code",
    "hash_access_token",
    "normalize_access_code",
    "verify_access_code",
    "verify_access_token",
]
