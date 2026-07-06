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
