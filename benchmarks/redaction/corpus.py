"""Labeled corpus for the pure-code redaction benchmark.

Every case declares the exact substrings that must NOT survive into storage
(`must_not_contain`). Soft-identifier cases additionally require that the value is
replaced by a *consistent* pseudonym rather than deleted, because person and org
names carry the entity graph and cannot simply be erased.

`tier` semantics:
  - ``direct``  high-risk identifier with no memory value -> must be erased
  - ``soft``    identity needed for the entity graph   -> must be pseudonymized
  - ``benign``  contains no PII                         -> must survive untouched
"""

from __future__ import annotations

from typing import Any


def _s(*parts: str) -> str:
    """Join secret fragments so the literal never appears in the repository.

    The redaction filter has to be exercised against byte-for-byte realistic
    credentials, but committing those literals trips GitHub push protection
    and correctly so. Assembling them at import time keeps the corpus
    functional while leaving no scannable secret in git history.
    """
    return "".join(parts)


_AWS_AKID = _s("AKIA", "IOSFODNN7EXAMPLE")
_GITHUB_PAT = _s("ghp_", "A1b2C3d4E5f6G7h8I9j0", "K1l2M3n4O5p6Q7r8")
_GITHUB_OAUTH = _s("gho_", "9Z8Y7X6W5V4U3T2S1R0", "Q9P8O7N6M5L4K3J2I1H0G")
_STRIPE_KEY = _s("sk_", "live_4eC39HqLyjWDarjtT1zdp7dc")
_STRIPE_PK = _s("pk_", "live_TYooMQauvdEDq54NiTphI7jx")
_SLACK_TOKEN = _s("xoxb-", "2847563190284-7391826350192-", "K3mQpR7vTzY8bW1cX6dF0gHj")
_OPENAI_CLASSIC = _s("sk-", "abcdefghijklmnopqrstuvwxyz1234567890AB")
_OPENAI_PROJ = _s("sk-", "proj-T9bK2mQ7xR4vL8nP3wZ6yH1jF5dS0aG2cE7uI4oK9lV3xN8")
_SENDGRID = _s("SG.", "ngeVfQFYQlKU0ufo8x5d1A.", "TwL2iGABf9DHoTf-09kqeF8tAmbihYzrnopKc-1s5cr")
_NPM_TOKEN = _s("npm_", "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")
_PEM_HEADER = _s("-----BEGIN ", "RSA PRIVATE KEY-----")

# fmt: off
CASES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- secrets
    {"case_id": "sec-aws-akid", "category": "aws_access_key", "tier": "direct",
     "text": f"Deploy script failed, the key {_AWS_AKID} was rejected by STS.",
     "must_not_contain": [_AWS_AKID]},
    {"case_id": "sec-aws-secret", "category": "aws_secret_key", "tier": "direct",
     "text": "Set aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY in the profile.",
     "must_not_contain": ["wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"]},
    {"case_id": "sec-github-pat", "category": "github_token", "tier": "direct",
     "text": f"Use {_GITHUB_PAT} for the release job.",
     "must_not_contain": [_GITHUB_PAT]},
    {"case_id": "sec-github-oauth", "category": "github_token", "tier": "direct",
     "text": f"The OAuth token {_GITHUB_OAUTH} leaked in the log.",
     "must_not_contain": [_GITHUB_OAUTH]},
    {"case_id": "sec-openai-classic", "category": "openai_key", "tier": "direct",
     "text": f"My openai key is {_OPENAI_CLASSIC} please rotate it.",
     "must_not_contain": [_OPENAI_CLASSIC]},
    {"case_id": "sec-openai-proj", "category": "openai_key", "tier": "direct",
     "text": f"export OPENAI_API_KEY={_OPENAI_PROJ}",
     "must_not_contain": [_OPENAI_PROJ]},
    {"case_id": "sec-stripe-live", "category": "payment_api_key", "tier": "direct",
     "text": f"Charged the card with {_STRIPE_KEY} as the stripe key.",
     "must_not_contain": [_STRIPE_KEY]},
    {"case_id": "sec-stripe-pk", "category": "payment_api_key", "tier": "direct",
     "text": f"pk_live_publishable key {_STRIPE_PK} is in the client bundle.",
     "must_not_contain": [_STRIPE_PK]},
    {"case_id": "sec-slack", "category": "slack_token", "tier": "direct",
     "text": f"Post to #ops with {_SLACK_TOKEN} using the bot token.",
     "must_not_contain": [_SLACK_TOKEN]},
    {"case_id": "sec-sendgrid", "category": "sendgrid_key", "tier": "direct",
     "text": f"Mailer failed with {_SENDGRID}",
     "must_not_contain": [_SENDGRID]},
    {"case_id": "sec-npm", "category": "npm_token", "tier": "direct",
     "text": f"npm publish failed, token {_NPM_TOKEN} rejected.",
     "must_not_contain": [_NPM_TOKEN]},
    {"case_id": "sec-jwt", "category": "jwt", "tier": "direct",
     "text": "Header carried eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U as bearer.",
     "must_not_contain": ["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"]},
    {"case_id": "sec-bearer", "category": "bearer_token", "tier": "direct",
     "text": "Call the API with Bearer abc123def456ghi789jkl012mno345pqr and retry.",
     "must_not_contain": ["abc123def456ghi789jkl012mno345pqr"]},
    {"case_id": "sec-password-kv", "category": "password", "tier": "direct",
     "text": "The connection string was password=Hunter2SuperSecret! and it failed.",
     "must_not_contain": ["Hunter2SuperSecret!"]},
    {"case_id": "sec-password-json", "category": "password", "tier": "direct",
     "text": 'Config block: {"username": "svc_ingest", "password": "Tr0ub4dor&3xyz", "port": 5432}',
     "must_not_contain": ["Tr0ub4dor&3xyz"]},
    {"case_id": "sec-otp", "category": "otp", "tier": "direct",
     "text": "Enter otp=482913 to finish the login, it expires soon.",
     "must_not_contain": ["482913"]},
    {"case_id": "sec-session", "category": "session_cookie", "tier": "direct",
     "text": "Cookie session=eyJhbGciOiJI9dGVzdCJ9abcXYZ123456789 was replayed.",
     "must_not_contain": ["eyJhbGciOiJI9dGVzdCJ9abcXYZ123456789"]},
    {"case_id": "sec-url-creds", "category": "url_credentials", "tier": "direct",
     "text": "Pull from postgres://appuser:s3cr3tp4ss@db.internal:5432/orders to migrate.",
     "must_not_contain": ["s3cr3tp4ss", "appuser:s3cr3tp4ss"]},
    {"case_id": "sec-privatekey", "category": "private_key", "tier": "direct",
     "text": f"PEM begins {_PEM_HEADER} MIIEowIBAAKCAQEA and must be revoked.",
     "must_not_contain": ["MIIEowIBAAKCAQEA"]},

    # ------------------------------------------------------------ direct PII
    {"case_id": "pii-email", "category": "email", "tier": "direct",
     "text": "Reach me at alice.smith+work@example.co.uk before Friday.",
     "must_not_contain": ["alice.smith+work@example.co.uk"]},
    {"case_id": "pii-email-obfuscated", "category": "email", "tier": "direct",
     "text": "Mail bob [at] mail [dot] com if the invoice is wrong.",
     "must_not_contain": ["bob [at] mail [dot] com"]},
    {"case_id": "pii-phone-e164", "category": "phone", "tier": "direct",
     "text": "Call +1 (415) 555-0132 or +44 20 7946 0958 tomorrow morning.",
     "must_not_contain": ["415", "555-0132", "7946 0958"]},
    {"case_id": "pii-phone-e164-bare", "category": "phone", "tier": "direct",
     "text": "My mobile is +919812345678 and I answer after six.",
     "must_not_contain": ["+919812345678"]},
    {"case_id": "pii-ssn", "category": "national_id", "tier": "direct",
     "text": "SSN 123-45-6789 appears on the W-9 form in the shared folder.",
     "must_not_contain": ["123-45-6789"]},
    {"case_id": "pii-aadhaar", "category": "national_id", "tier": "direct",
     "text": "Aadhaar number 2345 6789 0123 is needed for the KYC form.",
     "must_not_contain": ["2345 6789 0123"]},
    {"case_id": "pii-card-visa", "category": "payment_card", "tier": "direct",
     "text": "Card on file is 4111 1111 1111 1111 exp 04/29, use it for the refund.",
     "must_not_contain": ["4111 1111 1111 1111"]},
    {"case_id": "pii-card-amex", "category": "payment_card", "tier": "direct",
     "text": "Charge 378282246310005 for the annual plan.",
     "must_not_contain": ["378282246310005"]},
    {"case_id": "pii-iban", "category": "bank_account", "tier": "direct",
     "text": "Pay the invoice to GB82 WEST 1234 5698 7654 32 reference 8891.",
     "must_not_contain": ["GB82 WEST 1234 5698 7654 32", "GB82WEST12345698765432"]},
    {"case_id": "pii-routing", "category": "bank_account", "tier": "direct",
     "text": "Wire to routing 021000021, account 9876543210, bank in New York.",
     "must_not_contain": ["021000021", "9876543210"]},
    {"case_id": "pii-passport", "category": "passport", "tier": "direct",
     "text": "Passport number X12345678 expires in March, renewal booked.",
     "must_not_contain": ["X12345678"]},
    {"case_id": "pii-drivers-license", "category": "drivers_license", "tier": "direct",
     "text": "Driver's license D1234567 is scanned in the onboarding packet.",
     "must_not_contain": ["D1234567"]},
    {"case_id": "pii-dob", "category": "date_of_birth", "tier": "direct",
     "text": "Date of birth: 1985-07-14 makes them eligible for the senior plan.",
     "must_not_contain": ["1985-07-14"]},
    {"case_id": "pii-dob-worded", "category": "date_of_birth", "tier": "direct",
     "text": "Born on 14 July 1985, they prefer the morning slot.",
     "must_not_contain": ["14 July 1985"]},
    {"case_id": "pii-address", "category": "postal_address", "tier": "direct",
     "text": "Ship the replacement to 4521 Nagle Street, Apartment 3B, Portland.",
     "must_not_contain": ["4521 Nagle Street"]},
    {"case_id": "pii-address-uk", "category": "postal_address", "tier": "direct",
     "text": "Registered at 17 Baker Road, London SW1A 1AA, contact the solicitor.",
     "must_not_contain": ["17 Baker Road", "SW1A 1AA"]},
    {"case_id": "pii-ip-v4", "category": "network_identifier", "tier": "direct",
     "text": "The request came from 203.0.113.42 and our office is 192.168.1.10.",
     "must_not_contain": ["203.0.113.42", "192.168.1.10"]},
    {"case_id": "pii-ip-invalid-octet", "category": "benign", "tier": "benign",     "text": "Version string 999.888.777.666 is not an address, do not redact it.",
     "must_not_contain": [], "must_preserve": ["999.888.777.666"]},
    {"case_id": "pii-gps", "category": "precise_location", "tier": "direct",
     "text": "The van was last seen near 47.6062, -122.3321 at the loading bay.",
     "must_not_contain": ["47.6062", "-122.3321"]},
    {"case_id": "pii-mac", "category": "network_identifier", "tier": "direct",
     "text": "Bind the service to MAC address 00:1A:2B:3C:4D:5E on the lab VLAN.",
     "must_not_contain": ["00:1A:2B:3C:4D:5E"]},
    {"case_id": "pii-health", "category": "health_data", "tier": "direct",
     "text": "Diagnosed with type 2 diabetes in 2021 and on metformin since.",
     "must_not_contain": ["type 2 diabetes", "metformin"]},
    {"case_id": "pii-uuid-patient", "category": "national_id", "tier": "direct",
     "text": "Patient record 7f3a9c12-4b5d-4e6f-8a9b-0c1d2e3f4a5b was merged twice.",
     "must_not_contain": ["7f3a9c12-4b5d-4e6f-8a9b-0c1d2e3f4a5b"]},
    {"case_id": "pii-taxid", "category": "national_id", "tier": "direct",
     "text": "EIN 12-3456789 belongs to the contracting entity, not to me.",
     "must_not_contain": ["12-3456789"]},

    # -------------------------------------------------------------- soft PII
    {"case_id": "soft-selfintro", "category": "person_name", "tier": "soft",
     "text": "My name is Alice Johnson and I own the billing integration.",
     "must_not_contain": ["Alice Johnson"]},
    {"case_id": "soft-honorific", "category": "person_name", "tier": "soft",
     "text": "Dr. Robert Chen reviewed the schema and approved the change.",
     "must_not_contain": ["Robert Chen"]},
    {"case_id": "soft-consistency", "category": "person_name", "tier": "soft",
     "text": "Priya Raman leads the platform team. Priya said the migration is safe.",
     "must_not_contain": ["Priya Raman"]},
    {"case_id": "soft-org", "category": "organization", "tier": "soft",
     "text": "I work at Northwind Logistics Inc and we ship 400 parcels a day.",
     "must_not_contain": ["Northwind Logistics Inc"]},
    {"case_id": "soft-org-llc", "category": "organization", "tier": "soft",
     "text": "Contract signed with Cobalt Systems LLC for the data warehouse.",
     "must_not_contain": ["Cobalt Systems LLC"]},
    {"case_id": "soft-location", "category": "location", "tier": "soft",
     "text": "Based in Seattle, WA the team works fully remote since 2023.",
     "must_not_contain": ["Seattle, WA"]},
    {"case_id": "soft-email-plus-name", "category": "person_name", "tier": "soft",
     "text": "Marcus Webb is the escalation contact for the billing queue.",
     "must_not_contain": ["Marcus Webb"]},

    # --------------------------------------------------------------- benign
    {"case_id": "benign-shipping", "category": "benign", "tier": "benign",
     "text": "The package should arrive between Monday and Saturday after next.",
     "must_not_contain": [], "must_preserve": ["Monday", "Saturday after next"]},
    {"case_id": "benign-versions", "category": "benign", "tier": "benign",
     "text": "Upgraded to version 2.6.0 and build 18422 without regressions.",
     "must_not_contain": [], "must_preserve": ["2.6.0", "18422"]},
    {"case_id": "benign-quantities", "category": "benign", "tier": "benign",
     "text": "We processed 15420 records in 4 batches and dropped 37 duplicates.",
     "must_not_contain": [], "must_preserve": ["15420", "37"]},
    {"case_id": "benign-schedule", "category": "benign", "tier": "benign",
     "text": "Standup moved to 09:30 UTC on 2026-01-15 to suit the Berlin team.",
     "must_not_contain": [], "must_preserve": ["09:30", "2026-01-15", "Berlin"]},
    {"case_id": "benign-temp", "category": "benign", "tier": "benign",
     "text": "Warehouse stayed at 21.5 degrees overnight, humidity 60 percent.",
     "must_not_contain": [], "must_preserve": ["21.5", "60"]},
    {"case_id": "benign-http-status", "category": "benign", "tier": "benign",
     "text": "Endpoint returned 404 then 500, retried and finally 200 OK.",
     "must_not_contain": [], "must_preserve": ["404", "500", "200"]},
    {"case_id": "benign-hash", "category": "benign", "tier": "benign",
     "text": "Commit a1b2c3d4e5f6 changed the retry budget from 3 to 5 attempts.",
     "must_not_contain": [], "must_preserve": ["a1b2c3d4e5f6", "3", "5"]},
    {"case_id": "benign-ordinal", "category": "benign", "tier": "benign",
     "text": "She joined in March 2021 as the 14th engineer on the platform team.",
     "must_not_contain": [], "must_preserve": ["March 2021", "14th"]},
    {"case_id": "benign-env-var", "category": "benign", "tier": "benign",
     "text": "Set the api_key environment variable in the deployment manifest, not the repo.",
     "must_not_contain": [], "must_preserve": ["api_key"]},
    {"case_id": "benign-sentence-case", "category": "benign", "tier": "benign",
     "text": "The retrieval engine ranks dense vectors above lexical matches by default.",
     "must_not_contain": [], "must_preserve": ["retrieval engine", "dense vectors"]},
]
# fmt: on


def cases_by_tier(tier: str) -> list[dict[str, Any]]:
    return [case for case in CASES if case["tier"] == tier]
