package server

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/contexta/gateway/internal/auth"
	"github.com/contexta/gateway/internal/ratelimit"
)

type Server struct {
	Verifier    *auth.Verifier
	RateLimiter *ratelimit.RateLimiter
	DataPlane   string
	PythonAPI   string
	proxy       *Proxy
}

func New(verifier *auth.Verifier, rl *ratelimit.RateLimiter, dataPlane, pythonAPI string) *Server {
	return &Server{
		Verifier:    verifier,
		RateLimiter: rl,
		DataPlane:   dataPlane,
		PythonAPI:   pythonAPI,
		proxy:       &Proxy{},
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

		r.Route("/v1", func(r chi.Router) {
			r.Post("/observations", s.proxy.ReverseProxy(s.DataPlane))
			r.Post("/observations/batch", s.proxy.ReverseProxy(s.DataPlane))
			r.Post("/retrieve", s.proxy.ReverseProxy(s.DataPlane))
			r.Get("/context", s.proxy.ReverseProxy(s.DataPlane))
			r.Post("/sessions", s.proxy.ReverseProxy(s.DataPlane))
			r.Post("/sessions/{id}/end", s.proxy.ReverseProxy(s.DataPlane))
			r.Get("/sessions/inspect/{user_id}", s.proxy.ReverseProxy(s.DataPlane))

			r.Route("/memories/{id}", func(r chi.Router) {
				r.Get("/", s.proxy.ReverseProxy(s.DataPlane))
				r.Post("/pin", s.proxy.ReverseProxy(s.DataPlane))
				r.Post("/unpin", s.proxy.ReverseProxy(s.DataPlane))
				r.Post("/archive", s.proxy.ReverseProxy(s.DataPlane))
				r.Post("/restore", s.proxy.ReverseProxy(s.DataPlane))
				r.Delete("/", s.proxy.ReverseProxy(s.DataPlane))
				r.Get("/explain", s.proxy.ReverseProxy(s.DataPlane))
			})
		})

		r.Route("/api/v1", func(r chi.Router) {
			r.Post("/memories", s.proxy.ReverseProxy(s.PythonAPI))
			r.Put("/memories/{id}", s.proxy.ReverseProxy(s.PythonAPI))
			r.Post("/search", s.proxy.ReverseProxy(s.PythonAPI))
			r.Get("/memories/{id}", s.proxy.ReverseProxy(s.PythonAPI))
			r.Post("/memories/{id}/explain", s.proxy.ReverseProxy(s.PythonAPI))
			r.Post("/sessions", s.proxy.ReverseProxy(s.PythonAPI))
			r.Put("/sessions/{id}", s.proxy.ReverseProxy(s.PythonAPI))
			r.Get("/sessions/{id}", s.proxy.ReverseProxy(s.PythonAPI))
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
		if !key.HasScope("read") && !key.HasScope("write") && !key.HasScope("admin") {
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
