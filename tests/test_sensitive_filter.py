"""Tests for contexta.core.extraction.sensitive_filter module.

Comprehensive unit tests verifying detection and redaction of:
- Passwords
- One-time passwords (OTPs)
- Payment card numbers (Luhn-valid)
- API secrets/keys (AWS, GitHub, OpenAI, Stripe)
- Authentication tokens (JWT, Bearer)
- Session cookies
"""

import pytest

from contexta.core.extraction.sensitive_filter import (
    REDACTED,
    SensitiveDataFilter,
    _luhn_check,
    primary_scan,
    secondary_scan,
)


class TestLuhnCheck:
    """Verify Luhn algorithm implementation."""

    def test_valid_visa(self) -> None:
        assert _luhn_check("4111111111111111") is True

    def test_valid_mastercard(self) -> None:
        assert _luhn_check("5500000000000004") is True

    def test_valid_amex(self) -> None:
        assert _luhn_check("340000000000009") is True

    def test_invalid_number(self) -> None:
        assert _luhn_check("4111111111111112") is False

    def test_single_digit(self) -> None:
        # 0 is valid under Luhn
        assert _luhn_check("0") is True

    def test_all_zeros(self) -> None:
        assert _luhn_check("0000000000000000") is True


class TestPasswordDetection:
    """Verify password pattern detection and redaction."""

    def test_password_equals(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("password=mysecretpass123")
        assert REDACTED in result.redacted_content
        assert "mysecretpass123" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_passwd_colon(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("passwd: hunter2")
        assert REDACTED in result.redacted_content
        assert "hunter2" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_pwd_equals(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("pwd=abc123xyz")
        assert REDACTED in result.redacted_content
        assert "abc123xyz" not in result.redacted_content

    def test_password_with_quotes(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact('password="my_secret_pass"')
        assert "my_secret_pass" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_password_case_insensitive(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("PASSWORD=SuperSecret")
        assert "SuperSecret" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_password_in_json(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact('{"password": "s3cr3t_value"}')
        assert "s3cr3t_value" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_no_password_in_normal_text(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("The user discussed password policies.")
        # "policies" should not be redacted since it's not in key=value format
        # Actually the pattern matches "password policies" - let's check
        # The pattern requires = or : after password keyword
        # "password policies" doesn't match because there's no = or :
        # Wait - let me check: the pattern is (password|passwd|pwd)\s*[=:]\s*...
        # "password policies" has a space but no = or :, so it shouldn't match
        assert result.contains_sensitive_data is False


class TestOTPDetection:
    """Verify OTP pattern detection and redaction."""

    def test_otp_equals(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("otp=123456")
        assert "123456" not in result.redacted_content
        assert REDACTED in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_verification_code(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("verification_code: 789012")
        assert "789012" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_2fa_code(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("2fa_code=654321")
        assert "654321" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_code_is_pattern(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("Your code is 482910")
        assert "482910" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_mfa_code(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("mfa_code=112233")
        assert "112233" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_random_6_digits_not_in_otp_context(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("The population is 123456 people.")
        # No OTP context, should not be redacted
        assert result.contains_sensitive_data is False


class TestAPIKeyDetection:
    """Verify API key/secret detection and redaction."""

    def test_aws_access_key(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("AWS key: AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_github_pat(self) -> None:
        f = SensitiveDataFilter()
        token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = f.scan_and_redact(f"GitHub token: {token}")
        assert token not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_openai_key(self) -> None:
        f = SensitiveDataFilter()
        key = "sk-" + "proj1234567890abcdefghijklmnop"
        result = f.scan_and_redact(f"OPENAI_API_KEY={key}")
        assert key not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_stripe_live_secret(self) -> None:
        f = SensitiveDataFilter()
        key = "sk_" + "live_1234567890abcdefghijklmnop"
        result = f.scan_and_redact(f"stripe_key={key}")
        assert key not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_stripe_live_publishable(self) -> None:
        f = SensitiveDataFilter()
        key = "pk_" + "live_1234567890abcdefghijklmnop"
        result = f.scan_and_redact(f"publishable: {key}")
        assert key not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_generic_api_key(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("api_key=abcdef1234567890abcdef")
        assert "abcdef1234567890abcdef" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_generic_api_secret(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("api_secret: xyzzy1234567890abcdef")
        assert "xyzzy1234567890abcdef" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_secret_key_pattern(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact('secret_key="my_super_secret_key_value"')
        assert "my_super_secret_key_value" not in result.redacted_content
        assert result.contains_sensitive_data is True


class TestJWTDetection:
    """Verify JWT token detection and redaction."""

    def test_jwt_token(self) -> None:
        f = SensitiveDataFilter()
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = f.scan_and_redact(f"token: {jwt}")
        assert jwt not in result.redacted_content
        assert REDACTED in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_jwt_in_header(self) -> None:
        f = SensitiveDataFilter()
        jwt = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJtZW1lbnRvIn0.signature_value_here"
        result = f.scan_and_redact(f"Authorization: {jwt}")
        assert jwt not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_non_jwt_dots(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("version 1.2.3 is released")
        assert result.contains_sensitive_data is False


class TestBearerTokenDetection:
    """Verify Bearer token detection and redaction."""

    def test_bearer_token(self) -> None:
        f = SensitiveDataFilter()
        token = "abc123def456ghi789jkl012mno"
        result = f.scan_and_redact(f"Bearer {token}")
        assert token not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_bearer_case_insensitive(self) -> None:
        f = SensitiveDataFilter()
        token = "xyzzy1234567890abcdefghij"
        result = f.scan_and_redact(f"bearer {token}")
        assert token not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_authorization_header(self) -> None:
        f = SensitiveDataFilter()
        token = "v2_token_abcdefghijklmnopqrst"
        result = f.scan_and_redact(f"Authorization: Bearer {token}")
        assert token not in result.redacted_content
        assert result.contains_sensitive_data is True


class TestSessionCookieDetection:
    """Verify session cookie detection and redaction."""

    def test_session_equals(self) -> None:
        f = SensitiveDataFilter()
        session_val = "abc123def456ghi789jkl"
        result = f.scan_and_redact(f"session={session_val}")
        assert session_val not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_sid_equals(self) -> None:
        f = SensitiveDataFilter()
        sid_val = "s_1234567890abcdefghij"
        result = f.scan_and_redact(f"sid={sid_val}")
        assert sid_val not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_session_id_colon(self) -> None:
        f = SensitiveDataFilter()
        session_val = "sess_abcdefghijklmnop"
        result = f.scan_and_redact(f"session_id: {session_val}")
        assert session_val not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_session_token(self) -> None:
        f = SensitiveDataFilter()
        session_val = "tok_1234567890abcdefgh"
        result = f.scan_and_redact(f"session_token={session_val}")
        assert session_val not in result.redacted_content
        assert result.contains_sensitive_data is True


class TestPaymentCardDetection:
    """Verify payment card number detection and redaction."""

    def test_visa_card(self) -> None:
        f = SensitiveDataFilter()
        # Valid Visa test number
        result = f.scan_and_redact("Card: 4111111111111111")
        assert "4111111111111111" not in result.redacted_content
        assert REDACTED in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_mastercard(self) -> None:
        f = SensitiveDataFilter()
        # Valid Mastercard test number
        result = f.scan_and_redact("MC: 5500000000000004")
        assert "5500000000000004" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_amex_card(self) -> None:
        f = SensitiveDataFilter()
        # Valid Amex test number (15 digits)
        result = f.scan_and_redact("Amex: 340000000000009")
        assert "340000000000009" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_card_with_spaces(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("Card: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_card_with_dashes(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("Card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_invalid_luhn_not_redacted(self) -> None:
        f = SensitiveDataFilter()
        # This number fails Luhn check
        result = f.scan_and_redact("Number: 4111111111111112")
        assert "4111111111111112" in result.redacted_content
        assert result.contains_sensitive_data is False

    def test_short_number_not_redacted(self) -> None:
        f = SensitiveDataFilter()
        # 12 digits - too short for a card
        result = f.scan_and_redact("ID: 123456789012")
        # Should not be treated as a card number (< 13 digits)
        assert result.contains_sensitive_data is False


class TestMultiplePatterns:
    """Verify detection of multiple sensitive data types in one text."""

    def test_password_and_token(self) -> None:
        f = SensitiveDataFilter()
        content = "password=secret123 and token: Bearer abcdefghijklmnopqrstuvwxyz"
        result = f.scan_and_redact(content)
        assert "secret123" not in result.redacted_content
        assert "abcdefghijklmnopqrstuvwxyz" not in result.redacted_content
        assert result.contains_sensitive_data is True
        assert len(result.redaction_events) >= 2

    def test_api_key_and_card(self) -> None:
        f = SensitiveDataFilter()
        content = "key: AKIAIOSFODNN7EXAMPLE card: 4111111111111111"
        result = f.scan_and_redact(content)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_content
        assert "4111111111111111" not in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_all_types_combined(self) -> None:
        f = SensitiveDataFilter()
        content = (
            "password=hunter2 "
            "otp=123456 "
            "AKIAIOSFODNN7EXAMPLE "
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.rSWamyAYwuHCo7IFAgd1oRpSP7nzL7BF5t7ItqpKViM "
            "session=abcdefghijklmnopqrst "
            "4111111111111111"
        )
        result = f.scan_and_redact(content)
        assert "hunter2" not in result.redacted_content
        assert "123456" not in result.redacted_content
        assert "AKIAIOSFODNN7EXAMPLE" not in result.redacted_content
        assert "abcdefghijklmnopqrst" not in result.redacted_content
        assert "4111111111111111" not in result.redacted_content
        assert result.contains_sensitive_data is True


class TestNoSensitiveData:
    """Verify that normal text is not falsely flagged."""

    def test_normal_conversation(self) -> None:
        f = SensitiveDataFilter()
        content = "The user prefers Python over JavaScript for backend development."
        result = f.scan_and_redact(content)
        assert result.contains_sensitive_data is False
        assert result.redacted_content == content

    def test_technical_discussion(self) -> None:
        f = SensitiveDataFilter()
        content = "We should use PostgreSQL with pgvector for semantic search."
        result = f.scan_and_redact(content)
        assert result.contains_sensitive_data is False
        assert result.redacted_content == content

    def test_numbers_without_card_context(self) -> None:
        f = SensitiveDataFilter()
        content = "The project has 1234 stars and 567 forks."
        result = f.scan_and_redact(content)
        assert result.contains_sensitive_data is False

    def test_empty_string(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("")
        assert result.contains_sensitive_data is False
        assert result.redacted_content == ""


class TestPrimaryScan:
    """Verify the primary_scan convenience function."""

    def test_redacts_sensitive_data(self) -> None:
        result = primary_scan("password=secret123")
        assert "secret123" not in result.redacted_content
        assert REDACTED in result.redacted_content
        assert result.contains_sensitive_data is True

    def test_clean_content_passes_through(self) -> None:
        content = "Normal conversation about coding."
        result = primary_scan(content)
        assert result.redacted_content == content
        assert result.contains_sensitive_data is False


class TestSecondaryScan:
    """Verify the secondary_scan convenience function."""

    def test_detects_sensitive_data(self) -> None:
        assert secondary_scan("password=leaked_secret") is True

    def test_clean_content_passes(self) -> None:
        assert secondary_scan("User prefers dark mode.") is False

    def test_detects_api_key(self) -> None:
        assert secondary_scan("Found key AKIAIOSFODNN7EXAMPLE in output") is True

    def test_detects_jwt(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.rSWamyAYwuHCo7IFAgd1oRpSP7nzL7BF5t7ItqpKViM"
        assert secondary_scan(f"Token: {jwt}") is True


class TestRedactionCompleteness:
    """Verify that after redaction, no sensitive data remains."""

    def test_password_fully_redacted(self) -> None:
        f = SensitiveDataFilter()
        original_password = "SuperS3cr3t!Pass"
        content = f"password={original_password}"
        result = f.scan_and_redact(content)
        # After redaction, scanning again should find nothing
        second_scan = f.scan_and_redact(result.redacted_content)
        assert second_scan.contains_sensitive_data is False

    def test_api_key_fully_redacted(self) -> None:
        f = SensitiveDataFilter()
        content = "key: AKIAIOSFODNN7EXAMPLE"
        result = f.scan_and_redact(content)
        second_scan = f.scan_and_redact(result.redacted_content)
        assert second_scan.contains_sensitive_data is False

    def test_multiple_secrets_fully_redacted(self) -> None:
        f = SensitiveDataFilter()
        content = (
            "password=hunter2 "
            "api_key=abcdefghijklmnopqrst "
            "session=sess_1234567890abcdef"
        )
        result = f.scan_and_redact(content)
        second_scan = f.scan_and_redact(result.redacted_content)
        assert second_scan.contains_sensitive_data is False

    def test_card_number_fully_redacted(self) -> None:
        f = SensitiveDataFilter()
        content = "Pay with 4111111111111111"
        result = f.scan_and_redact(content)
        second_scan = f.scan_and_redact(result.redacted_content)
        assert second_scan.contains_sensitive_data is False


class TestRedactionEvents:
    """Verify that redaction events are properly recorded."""

    def test_password_event_type(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("password=secret")
        assert any(e.pattern_type == "password" for e in result.redaction_events)

    def test_api_key_event_type(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("AKIAIOSFODNN7EXAMPLE")
        assert any(e.pattern_type == "api_key" for e in result.redaction_events)

    def test_jwt_event_type(self) -> None:
        f = SensitiveDataFilter()
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.rSWamyAYwuHCo7IFAgd1oRpSP7nzL7BF5t7ItqpKViM"
        result = f.scan_and_redact(jwt)
        assert any(e.pattern_type == "jwt" for e in result.redaction_events)

    def test_card_event_type(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("4111111111111111")
        assert any(e.pattern_type == "payment_card" for e in result.redaction_events)

    def test_event_records_length(self) -> None:
        f = SensitiveDataFilter()
        result = f.scan_and_redact("password=hunter2")
        password_events = [e for e in result.redaction_events if e.pattern_type == "password"]
        assert len(password_events) == 1
        assert password_events[0].original_length == len("hunter2")
