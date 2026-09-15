package server

import (
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"
)

type Proxy struct{}

func (p *Proxy) ReverseProxy(target string) http.HandlerFunc {
	targetURL, err := url.Parse(target)
	if err != nil {
		slog.Error("invalid proxy target", "target", target, "error", err)
		return func(w http.ResponseWriter, r *http.Request) {
			writeError(w, http.StatusInternalServerError, "proxy configuration error")
		}
	}

	proxy := httputil.NewSingleHostReverseProxy(targetURL)
	proxy.FlushInterval = 100 * time.Millisecond

	return func(w http.ResponseWriter, r *http.Request) {
		r.Header.Set("X-Forwarded-For", r.RemoteAddr)
		r.Header.Set("X-Forwarded-Proto", r.URL.Scheme)

		proxy.ServeHTTP(w, r)
	}
}

// StripPrefixReverseProxy forwards to target after stripping prefix,
// so Gateway route /api/v1/memories reaches Python /v1/memories.
func (p *Proxy) StripPrefixReverseProxy(target, prefix string) http.HandlerFunc {
	targetURL, err := url.Parse(target)
	if err != nil {
		slog.Error("invalid proxy target", "target", target, "error", err)
		return func(w http.ResponseWriter, r *http.Request) {
			writeError(w, http.StatusInternalServerError, "proxy configuration error")
		}
	}

	proxy := httputil.NewSingleHostReverseProxy(targetURL)
	proxy.FlushInterval = 100 * time.Millisecond

	return func(w http.ResponseWriter, r *http.Request) {
		r.Header.Set("X-Forwarded-For", r.RemoteAddr)
		r.Header.Set("X-Forwarded-Proto", r.URL.Scheme)
		r.URL.Path = trimPrefix(r.URL.Path, prefix)
		if r.URL.Path == "" {
			r.URL.Path = "/"
		}
		if r.URL.RawPath != "" {
			r.URL.RawPath = trimPrefix(r.URL.RawPath, prefix)
			if r.URL.RawPath == "" {
				r.URL.RawPath = "/"
			}
		}

		proxy.ServeHTTP(w, r)
	}
}

func trimPrefix(path, prefix string) string {
	if len(path) >= len(prefix) && path[:len(prefix)] == prefix {
		return path[len(prefix):]
	}
	return path
}
