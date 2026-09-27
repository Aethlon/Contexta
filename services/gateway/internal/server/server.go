package server

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/contexta/gateway/internal/auth"
	"github.com/contexta/gateway/internal/ratelimit"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

type Server struct {
	Verifier    *auth.Verifier
	RateLimiter *ratelimit.RateLimiter
	PythonAPI   string
	proxy       *Proxy
	Cache       *RetrievalCache
}

func New(verifier *auth.Verifier, rl *ratelimit.RateLimiter, pythonAPI string) *Server {
	return &Server{
		Verifier:    verifier,
		RateLimiter: rl,
		PythonAPI:   pythonAPI,
		proxy:       &Proxy{},
	}
}

// SetCache attaches the retrieval response cache. Without it the gateway is a
// plain proxy, so this is safe to leave unset.
func (s *Server) SetCache(client RedisClient, ttl time.Duration) {
	if client == nil {
		return
	}
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	s.Cache = &RetrievalCache{redis: client, ttl: ttl}
}

// cached wraps a proxy handler with the response cache and single-flight.
func (s *Server) cached(handler http.HandlerFunc) http.HandlerFunc {
	wrapped := CachedProxy(handler, s.Cache)
	return func(w http.ResponseWriter, r *http.Request) {
		wrapped.ServeHTTP(w, r)
	}
}

func (s *Server) RegisterRoutes(r chi.Router) {
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(60 * time.Second))

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok"}`))
	})

	r.Get("/readyz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ready"}`))
	})

	r.Get("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`# gateway metrics placeholder`))
	})

	r.Group(func(r chi.Router) {
		r.Use(s.Verifier.Middleware)
		r.Use(s.RateLimiter.Middleware)
		r.Use(s.scopeMiddleware)
		r.Use(s.internalHeadersMiddleware)

		// The gateway is a stateless edge: every application route is reverse
		// proxied to the Python API, which is the sole data path. The Go layer
		// holds no storage, no staging tables, and no retrieval implementation.
		// The Python API exposes these same paths, so no prefix rewriting is
		// needed for /v1 (unlike the /api/v1 aliases below).
		r.Route("/v1", func(r chi.Router) {
			r.Post("/observations", s.proxy.ReverseProxy(s.PythonAPI))
			r.Post("/observations/batch", s.proxy.ReverseProxy(s.PythonAPI))
			// Read paths go through the edge cache: identical recall queries inside
			// the TTL are served from Redis, and concurrent duplicates are coalesced
			// into a single upstream request so the model server sees one embedding
			// call instead of N.
			r.Post("/retrieve", s.cached(s.proxy.ReverseProxy(s.PythonAPI)))
			r.Post("/retrieve/batch", s.cached(s.proxy.ReverseProxy(s.PythonAPI)))
			// Upstream has no GET /v1/context handler; the implemented context
			// bundle lives at GET /v1/memories/context. Kept registered so the
			// gateway route table stays stable, but it answers 404 upstream.
			r.Get("/context", s.proxy.ReverseProxy(s.PythonAPI))
			r.Post("/sessions", s.proxy.ReverseProxy(s.PythonAPI))
			r.Post("/sessions/{id}/end", s.proxy.ReverseProxy(s.PythonAPI))
			r.Get("/sessions/inspect/{user_id}", s.proxy.ReverseProxy(s.PythonAPI))

			r.Route("/memories/{id}", func(r chi.Router) {
				r.Get("/", s.proxy.ReverseProxy(s.PythonAPI))
				r.Post("/pin", s.proxy.ReverseProxy(s.PythonAPI))
				r.Post("/unpin", s.proxy.ReverseProxy(s.PythonAPI))
				r.Post("/archive", s.proxy.ReverseProxy(s.PythonAPI))
				r.Post("/restore", s.proxy.ReverseProxy(s.PythonAPI))
				r.Delete("/", s.proxy.ReverseProxy(s.PythonAPI))
				r.Get("/explain", s.proxy.ReverseProxy(s.PythonAPI))
			})
		})

		r.Route("/api/v1", func(r chi.Router) {
			r.Post("/memories", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Put("/memories/{id}", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Post("/search", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Get("/memories/{id}", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Post("/memories/{id}/explain", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Post("/sessions", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Put("/sessions/{id}", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
			r.Get("/sessions/{id}", s.proxy.StripPrefixReverseProxy(s.PythonAPI, "/api"))
		})
	})
}

func (s *Server) internalHeadersMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := auth.APIKeyFromContext(r.Context())
		if key == nil {
			writeError(w, http.StatusUnauthorized, "unauthorized")
			return
		}
		r.Header.Set("X-Mem-Tenant-Id", key.TenantID)
		r.Header.Set("X-Mem-Actor-Id", key.ActorID)
		r.Header.Set("X-Mem-Key-Id", key.KeyID)
		r.Header.Set("X-Mem-Scopes", key.Scopes)
		r.Header.Set("X-Mem-Trace-Id", r.Header.Get("X-Request-ID"))
		// Also set canonical headers so Python API middleware accepts proxied requests.
		r.Header.Set("x-organization-id", key.TenantID)
		r.Header.Set("x-user-id", key.ActorID)
		next.ServeHTTP(w, r)
	})
}

func (s *Server) scopeMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := auth.APIKeyFromContext(r.Context())
		if key == nil {
			writeError(w, http.StatusUnauthorized, "unauthorized")
			return
		}
		if !key.HasScope("read") && !key.HasScope("write") && !key.HasScope("admin") && !key.HasScope("observe") && !key.HasScope("retrieve") {
			writeError(w, http.StatusForbidden, "insufficient scopes")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	w.Write([]byte(`{"error":"` + msg + `"}`))
	slog.Warn("request rejected", "status", status, "reason", msg)
}
