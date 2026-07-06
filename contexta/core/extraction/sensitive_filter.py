"""Sensitive data detection and redaction for the contexta memory engine.

This module provides pattern-based detection and redaction of sensitive data
including passwords, OTPs, payment card numbers, API secrets, authentication
tokens, and session cookies. It is used in two stages:

1. Primary scan: runs on observation payload content before enqueue, redacts in-place.
2. Secondary scan: runs on extracted memory content after LLM extraction.
   If sensitive data is detected, the memory is discarded and a security event is logged.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"


@dataclass
class RedactionEvent:
    """Record of a single redaction performed on content."""

    pattern_type: str
    original_length: int
    position: int


@dataclass
class ScanResult:
    """Result of a sensitive data scan."""

    contains_sensitive_data: bool
    redacted_content: str
    redaction_events: list[RedactionEvent] = field(default_factory=list)


def _luhn_check(number: str) -> bool:
    """Validate a number string using the Luhn algorithm."""
    digits = [int(d) for d in number]
    # Reverse, double every second digit from the right
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        doubled = d * 2
        total += doubled - 9 if doubled > 9 else doubled
    return total % 10 == 0


class SensitiveDataFilter:
    """Pattern-based sensitive data detection and redaction.

    Detects:
    - Passwords (password=, passwd:, pwd= patterns)
    - One-time passwords (OTPs) in OTP context
    - Payment card numbers (Luhn-valid, 13-19 digits)
    - API secrets/keys (AWS, GitHub, OpenAI, Stripe)
    - Authentication tokens (JWT, Bearer)
    - Session cookies (session=, sid= patterns)
    """

    # Password patterns: password=..., passwd:..., pwd=...
    _PASSWORD_PATTERNS = [
        re.compile(
            r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?(?!\[REDACTED\])([^\s"\',;}{)\]]+)["\']?'
        ),
        # JSON-style: "password": "value"
        re.compile(
            r'(?i)["\'](password|passwd|pwd)["\']\s*:\s*["\'](?!\[REDACTED\])([^"\']+)["\']'
        ),
    ]

    # OTP patterns: 6-digit codes in OTP context
    _OTP_PATTERNS = [
        re.compile(r"(?i)(otp|one[_\-\s]?time[_\-\s]?password|verification[_\-\s]?code|2fa[_\-\s]?code|mfa[_\-\s]?code)\s*[=:]\s*[\"']?(\d{4,8})[\"']?"),
        re.compile(r"(?i)(?:code|token)\s+(?:is|was|:)\s*[\"']?(\d{6})[\"']?"),
    ]

    # API key patterns
    _API_KEY_PATTERNS = [
        # AWS Access Key ID
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
        # GitHub personal access token
        re.compile(r"\b(ghp_[A-Za-z0-9]{36,})\b"),
        # GitHub OAuth token
        re.compile(r"\b(gho_[A-Za-z0-9]{36,})\b"),
        # OpenAI API key
        re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
        # Stripe keys
        re.compile(r"\b(sk_live_[A-Za-z0-9]{20,})\b"),
        re.compile(r"\b(pk_live_[A-Za-z0-9]{20,})\b"),
        re.compile(r"\b(sk_test_[A-Za-z0-9]{20,})\b"),
        re.compile(r"\b(pk_test_[A-Za-z0-9]{20,})\b"),
        # Generic API key/secret patterns
        re.compile(
            r'(?i)(api[_\-]?key|api[_\-]?secret|secret[_\-]?key)\s*[=:]\s*["\']?(?!\[REDACTED\])([A-Za-z0-9_\-]{16,})["\']?'
        ),
    ]

    # JWT pattern: three base64url segments separated by dots
    _JWT_PATTERN = re.compile(
        r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-]{10,})\b"
    )

    # Bearer token pattern
    _BEARER_PATTERN = re.compile(
        r"(?i)(Bearer\s+)([A-Za-z0-9_\-\.]{20,})"
    )

    # Session cookie patterns
    _SESSION_PATTERNS = [
        re.compile(
            r'(?i)(session|session[_\-]?id|sid|session[_\-]?token)\s*[=:]\s*["\']?(?!\[REDACTED\])([A-Za-z0-9_\-\.]{16,})["\']?'
        ),
    ]

    # Payment card number pattern (13-19 digits, possibly separated by spaces or dashes)
    _CARD_NUMBER_PATTERN = re.compile(
        r"\b(\d[ \-]?){12,18}\d\b"
    )

    def _might_contain_sensitive_data(self, content: str) -> bool:
        """Fast precheck to avoid expensive regex scans on clearly plain text."""
        lowered = content.lower()
        indicators = (
            "password",
            "passwd",
            "pwd",
            "otp",
            "one-time",
            "one_time",
            "verification",
            "2fa",
            "mfa",
            "code",
            "api",
            "secret",
            "key",
            "akia",
            "ghp_",
            "gho_",
            "sk-",
            "sk_live_",
            "pk_live_",
            "sk_test_",
            "pk_test_",
            "bearer",
            "session",
            "sid",
            "eyj",
            "token",
        )
        if any(indicator in lowered for indicator in indicators):
            return True

        digit_count = sum(char.isdigit() for char in content)
        return digit_count >= 13

    def scan_and_redact(self, content: str) -> ScanResult:
        """Scan content for sensitive data and redact any findings.

        This is used for the primary scan during observation ingestion.
        Sensitive values are replaced with [REDACTED] in-place.

        Args:
            content: The text content to scan.

        Returns:
            ScanResult with redacted content and list of redaction events.
        """
        redaction_events: list[RedactionEvent] = []
        if not self._might_contain_sensitive_data(content):
            return ScanResult(
                contains_sensitive_data=False,
                redacted_content=content,
                redaction_events=redaction_events,
            )

        redacted = content

        # Redact passwords
        redacted, events = self._redact_passwords(redacted)
        redaction_events.extend(events)

        # Redact OTPs
        redacted, events = self._redact_otps(redacted)
        redaction_events.extend(events)

        # Redact API keys
        redacted, events = self._redact_api_keys(redacted)
        redaction_events.extend(events)

        # Redact JWTs
        redacted, events = self._redact_jwts(redacted)
        redaction_events.extend(events)

        # Redact Bearer tokens
        redacted, events = self._redact_bearer_tokens(redacted)
        redaction_events.extend(events)

        # Redact session cookies
        redacted, events = self._redact_session_cookies(redacted)
        redaction_events.extend(events)

        # Redact payment card numbers (must be after other patterns to avoid false positives)
        redacted, events = self._redact_card_numbers(redacted)
        redaction_events.extend(events)

        return ScanResult(
            contains_sensitive_data=len(redaction_events) > 0,
            redacted_content=redacted,
            redaction_events=redaction_events,
        )

    def contains_sensitive_data(self, content: str) -> bool:
        """Check if content contains any sensitive data patterns.

        This is used for the secondary scan after LLM extraction.
        Does not modify the content, only detects presence.

        Args:
            content: The text content to check.

        Returns:
            True if sensitive data patterns are detected.
        """
        result = self.scan_and_redact(content)
        return result.contains_sensitive_data

    def _redact_passwords(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact password patterns."""
        events: list[RedactionEvent] = []
        result = content
        for pattern in self._PASSWORD_PATTERNS:
            for match in pattern.finditer(result):
                # Group 2 is the password value
                password_value = match.group(2)
                events.append(
                    RedactionEvent(
                        pattern_type="password",
                        original_length=len(password_value),
                        position=match.start(2),
                    )
                )
            # Replace only the password value (group 2), keeping everything else
            result = pattern.sub(
                lambda m: m.group(0).replace(m.group(2), REDACTED),
                result,
            )
        return result, events

    def _redact_otps(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact OTP patterns."""
        events: list[RedactionEvent] = []
        result = content

        # Pattern 1: otp=123456 style
        pattern = self._OTP_PATTERNS[0]
        for match in pattern.finditer(result):
            otp_value = match.group(2)
            events.append(
                RedactionEvent(
                    pattern_type="otp",
                    original_length=len(otp_value),
                    position=match.start(2),
                )
            )
        result = pattern.sub(
            lambda m: m.group(0).replace(m.group(2), REDACTED),
            result,
        )

        # Pattern 2: "code is 123456" style
        pattern = self._OTP_PATTERNS[1]
        for match in pattern.finditer(result):
            otp_value = match.group(1)
            events.append(
                RedactionEvent(
                    pattern_type="otp",
                    original_length=len(otp_value),
                    position=match.start(1),
                )
            )
        result = pattern.sub(
            lambda m: m.group(0).replace(m.group(1), REDACTED),
            result,
        )

        return result, events

    def _redact_api_keys(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact API key patterns."""
        events: list[RedactionEvent] = []
        result = content

        for pattern in self._API_KEY_PATTERNS:
            for match in pattern.finditer(result):
                # For patterns with 2 groups (key=value), redact group 2
                # For patterns with 1 group (standalone key), redact group 1
                if pattern.groups >= 2:
                    try:
                        secret_value = match.group(2)
                        pos = match.start(2)
                    except IndexError:
                        secret_value = match.group(1)
                        pos = match.start(1)
                else:
                    secret_value = match.group(1)
                    pos = match.start(1)

                events.append(
                    RedactionEvent(
                        pattern_type="api_key",
                        original_length=len(secret_value),
                        position=pos,
                    )
                )

            # Replace the sensitive value
            if pattern.groups >= 2:
                # Check if this pattern actually captures 2 groups
                test_match = pattern.search(result)
                if test_match and test_match.lastindex and test_match.lastindex >= 2:
                    result = pattern.sub(
                        lambda m: m.group(0).replace(m.group(2), REDACTED)
                        if m.lastindex and m.lastindex >= 2
                        else m.group(0).replace(m.group(1), REDACTED),
                        result,
                    )
                else:
                    result = pattern.sub(
                        lambda m: m.group(0).replace(m.group(1), REDACTED),
                        result,
                    )
            else:
                result = pattern.sub(REDACTED, result)

        return result, events

    def _redact_jwts(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact JWT tokens."""
        events: list[RedactionEvent] = []
        result = content

        for match in self._JWT_PATTERN.finditer(result):
            events.append(
                RedactionEvent(
                    pattern_type="jwt",
                    original_length=len(match.group(1)),
                    position=match.start(1),
                )
            )

        result = self._JWT_PATTERN.sub(REDACTED, result)
        return result, events

    def _redact_bearer_tokens(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact Bearer tokens."""
        events: list[RedactionEvent] = []
        result = content

        for match in self._BEARER_PATTERN.finditer(result):
            token_value = match.group(2)
            events.append(
                RedactionEvent(
                    pattern_type="bearer_token",
                    original_length=len(token_value),
                    position=match.start(2),
                )
            )

        result = self._BEARER_PATTERN.sub(
            lambda m: f"{m.group(1)}{REDACTED}",
            result,
        )
        return result, events

    def _redact_session_cookies(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact session cookie patterns."""
        events: list[RedactionEvent] = []
        result = content

        for pattern in self._SESSION_PATTERNS:
            for match in pattern.finditer(result):
                session_value = match.group(2)
                events.append(
                    RedactionEvent(
                        pattern_type="session_cookie",
                        original_length=len(session_value),
                        position=match.start(2),
                    )
                )
            result = pattern.sub(
                lambda m: m.group(0).replace(m.group(2), REDACTED),
                result,
            )

        return result, events

    def _redact_card_numbers(self, content: str) -> tuple[str, list[RedactionEvent]]:
        """Detect and redact payment card numbers (Luhn-valid)."""
        events: list[RedactionEvent] = []
        result = content

        for match in self._CARD_NUMBER_PATTERN.finditer(result):
            raw_number = match.group(0)
            # Strip spaces and dashes to get pure digits
            digits_only = re.sub(r"[\s\-]", "", raw_number)

            # Must be 13-19 digits and pass Luhn check
            if 13 <= len(digits_only) <= 19 and _luhn_check(digits_only):
                events.append(
                    RedactionEvent(
                        pattern_type="payment_card",
                        original_length=len(raw_number),
                        position=match.start(),
                    )
                )

        # Second pass to actually redact (to avoid offset issues)
        def _replace_card(match: re.Match) -> str:
            raw_number = match.group(0)
            digits_only = re.sub(r"[\s\-]", "", raw_number)
            if 13 <= len(digits_only) <= 19 and _luhn_check(digits_only):
                return REDACTED
            return raw_number

        result = self._CARD_NUMBER_PATTERN.sub(_replace_card, result)
        return result, events


def primary_scan(content: str) -> ScanResult:
    """Perform primary sensitive data scan on observation payload content.

    This is called before enqueuing the observation for extraction.
    Redacts sensitive data in-place.

    Args:
        content: Raw observation payload content.

    Returns:
        ScanResult with redacted content and redaction events.
    """
    filter_instance = SensitiveDataFilter()
    result = filter_instance.scan_and_redact(content)

    if result.contains_sensitive_data:
        logger.info(
            "Primary scan: redacted %d sensitive data occurrences",
            len(result.redaction_events),
        )

    return result


def secondary_scan(content: str) -> bool:
    """Perform secondary sensitive data scan on extracted memory content.

    This is called after LLM extraction. If sensitive data is detected,
    the memory should be discarded and a security event logged.

    Args:
        content: Extracted memory content.

    Returns:
        True if sensitive data is detected (memory should be discarded).
    """
    filter_instance = SensitiveDataFilter()
    has_sensitive = filter_instance.contains_sensitive_data(content)

    if has_sensitive:
        logger.warning(
            "Secondary scan: sensitive data detected in extracted memory. "
            "Memory will be discarded. Security event logged."
        )

    return has_sensitive
