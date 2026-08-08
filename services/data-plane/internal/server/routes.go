package server

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

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
		if err := s.Store.Pool.Ping(r.Context()); err != nil {
			slog.Error("readiness check failed", "error", err)
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ready"}`))
	})

	r.Route("/v1", func(r chi.Router) {
		r.Use(s.internalHeadersMiddleware)

		r.Post("/observations", s.IngestObservation)
		r.Post("/observations/batch", s.IngestBatch)
		r.Post("/retrieve", s.Retrieve)
		r.Get("/context", s.Context)
		r.Post("/sessions", s.CreateSession)
		r.Post("/sessions/{id}/end", s.EndSession)
		r.Get("/sessions/inspect/{user_id}", s.InspectSessions)

		r.Route("/memories/{id}", func(r chi.Router) {
			r.Get("/", s.GetMemory)
			r.Post("/pin", s.PinMemory)
			r.Post("/unpin", s.UnpinMemory)
			r.Post("/archive", s.ArchiveMemory)
			r.Post("/restore", s.RestoreMemory)
			r.Delete("/", s.DeleteMemory)
			r.Get("/explain", s.ExplainMemory)
		})
	})
}

func (s *Server) internalHeadersMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r.Header.Set("X-Mem-Tenant-Id", r.Header.Get("X-Mem-Tenant-Id"))
		r.Header.Set("X-Mem-Actor-Id", r.Header.Get("X-Mem-Actor-Id"))
		r.Header.Set("X-Mem-Key-Id", r.Header.Get("X-Mem-Key-Id"))
		r.Header.Set("X-Mem-Scopes", r.Header.Get("X-Mem-Scopes"))
		next.ServeHTTP(w, r)
	})
}
