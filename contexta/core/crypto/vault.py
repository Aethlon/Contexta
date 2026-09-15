"""Sovereign Vault Cryptography: On-the-fly authenticated encryption & cryptographic shredding.

Uses an HMAC-SHA256 authenticated keystream stream cipher with per-message random nonces
and constant-time MAC verification. Zero external C-extensions required.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from contexta.config.settings import get_settings


def _derive_vault_key(org_id: str | None = None) -> bytes:
    """Derive an encryption key from the system secret key and optional organization/tenant context."""
    settings = get_settings()
    master = settings.secret_key.encode("utf-8")
    salt = (org_id or "contexta-default-vault").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", master, salt, iterations=100_000, dklen=32)


def encrypt_content(text: str | None, org_id: str | None = None) -> str | None:
    """Encrypt plaintext on-the-fly before storing in the database."""
    if text is None:
        return None
    if text.startswith("enc:v1:"):
        return text  # already encrypted

    key = _derive_vault_key(org_id)
    nonce = os.urandom(16)
    data = text.encode("utf-8")

    blocks = []
    counter = 0
    while len(blocks) * 32 < len(data):
        blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1

    keystream = b"".join(blocks)[:len(data)]
    ciphertext = bytes(a ^ b for a, b in zip(data, keystream))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()

    raw_payload = nonce + tag + ciphertext
    return "enc:v1:" + base64.urlsafe_b64encode(raw_payload).decode("utf-8")


def decrypt_content(token: str | None, org_id: str | None = None) -> str | None:
    """Decrypt ciphertext retrieved from the database."""
    if token is None:
        return None
    if not token.startswith("enc:v1:"):
        return token  # legacy or unencrypted plain-text

    key = _derive_vault_key(org_id)
    try:
        raw_payload = base64.urlsafe_b64decode(token[7:])
        if len(raw_payload) < 48:
            return token

        nonce = raw_payload[:16]
        tag = raw_payload[16:48]
        ciphertext = raw_payload[48:]

        expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            return "[Encrypted - Decryption Key Mismatch]"

        blocks = []
        counter = 0
        while len(blocks) * 32 < len(ciphertext):
            blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1

        keystream = b"".join(blocks)[:len(ciphertext)]
        decrypted_bytes = bytes(a ^ b for a, b in zip(ciphertext, keystream))
        return decrypted_bytes.decode("utf-8", errors="replace")
    except Exception:
        return token
