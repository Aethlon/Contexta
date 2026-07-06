package redaction

import "regexp"

type Filter struct {
	patterns []*regexp.Regexp
}

func NewFilter() *Filter {
	return &Filter{
		patterns: []*regexp.Regexp{
			// API keys: sk-... (OpenAI), xox[baprs]-... (Slack), etc.
			regexp.MustCompile(`(?i)(sk-[A-Za-z0-9]{20,})`),
			regexp.MustCompile(`(?i)(xox[baprs]?-?[A-Za-z0-9]{12,})`),
			regexp.MustCompile(`(?i)(gh[pousr]_[A-Za-z0-9]{36,})`),
			regexp.MustCompile(`(?i)(AKIA[0-9A-Z]{16})`),

			// JWTs and Bearer tokens
			regexp.MustCompile(`(?i)Bearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}`),
			regexp.MustCompile(`(?i)(eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+)`),

			// Passwords and secrets
			regexp.MustCompile(`(?i)(password[=:]\s*['"]?[^\s'"]{4,})`),
			regexp.MustCompile(`(?i)(secret[=:]\s*['"]?[^\s'"]{4,})`),
			regexp.MustCompile(`(?i)(passwd[=:]\s*['"]?[^\s'"]{4,})`),
			regexp.MustCompile(`(?i)(pwd[=:]\s*['"]?[^\s'"]{4,})`),

			// Credit cards
			regexp.MustCompile(`\b(?:\d{4}[-\s]?){3}\d{4}\b`),

			// OTP / 2FA codes (6-8 digits)
			regexp.MustCompile(`\b\d{6,8}\b`),

			// Private keys
			regexp.MustCompile(`-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)\s+PRIVATE\s+KEY-----`),

			// Connection strings and URLs with credentials
			regexp.MustCompile(`(?i)(postgresql?|redis|mysql|mongodb)://[^\s]+`),
			regexp.MustCompile(`(?i)(https?://)[^:]+:[^@]+@`),

			// Session tokens and cookies
			regexp.MustCompile(`(?i)(session[=:]\s*['"]?[A-Za-z0-9]{16,})`),
			regexp.MustCompile(`(?i)(token[=:]\s*['"]?[A-Za-z0-9]{16,})`),
		},
	}
}

func (f *Filter) Apply(content *string) (string, bool) {
	changed := false
	for _, re := range f.patterns {
		if re.MatchString(*content) {
			changed = true
			*content = re.ReplaceAllString(*content, "[REDACTED]")
		}
	}
	return *content, changed
}
