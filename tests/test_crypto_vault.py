import pytest
from contexta.core.crypto.vault import encrypt_content, decrypt_content, _derive_vault_key


def test_vault_key_derivation():
    k1 = _derive_vault_key("org-1")
    k2 = _derive_vault_key("org-1")
    k3 = _derive_vault_key("org-2")
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 32


def test_encrypt_decrypt_roundtrip():
    org = "sovereign-org-1"
    raw_text = "User preferences: TypeScript, Dark mode, No telemetry."
    
    ciphertext = encrypt_content(raw_text, org)
    assert ciphertext.startswith("enc:v1:")
    assert raw_text not in ciphertext
    
    decrypted = decrypt_content(ciphertext, org)
    assert decrypted == raw_text


def test_encrypt_different_nonces():
    org = "sovereign-org-1"
    raw_text = "Same plaintext memory"
    
    c1 = encrypt_content(raw_text, org)
    c2 = encrypt_content(raw_text, org)
    # Different nonces ensure distinct ciphertexts
    assert c1 != c2
    assert decrypt_content(c1, org) == raw_text
    assert decrypt_content(c2, org) == raw_text


def test_decrypt_tampered_ciphertext():
    org = "sovereign-org-1"
    raw_text = "Sensitive medical or financial note"
    ciphertext = encrypt_content(raw_text, org)
    
    # Tamper with the base64 payload body
    header = "enc:v1:"
    payload = ciphertext[len(header):]
    tampered_payload = payload[:-4] + ("AAAA" if not payload.endswith("AAAA") else "BBBB")
    tampered = header + tampered_payload
    
    res = decrypt_content(tampered, org)
    assert res == "[Encrypted - Decryption Key Mismatch]" or res.startswith("enc:v1:")


def test_decrypt_wrong_org_key():
    ciphertext = encrypt_content("Secret info", "org-alpha")
    res = decrypt_content(ciphertext, "org-beta")
    assert res == "[Encrypted - Decryption Key Mismatch]"


def test_decrypt_unencrypted_passthrough():
    plaintext = "Legacy unencrypted string"
    assert decrypt_content(plaintext, "any-org") == plaintext
    assert decrypt_content(None, "any-org") is None
    assert encrypt_content(None, "any-org") is None
