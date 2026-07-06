package server

import (
	"log/slog"
	"net/http"

	"github.com/contexta/data-plane/internal/metering"
	"github.com/contexta/data-plane/internal/redaction"
	"github.com/contexta/data-plane/internal/storage"
)

type Server struct {
	Store   *storage.Store
	Filter  *redaction.Filter
	Emitter *metering.Emitter
}

func New(store *storage.Store, filter *redaction.Filter, emitter *metering.Emitter) *Server {
	return &Server{
		Store:   store,
		Filter:  filter,
		Emitter: emitter,
	}
}

func (s *Server) tenantID(r *http.Request) string {
	return r.Header.Get("X-Mem-Tenant-Id")
}

func (s *Server) actorID(r *http.Request) string {
	return r.Header.Get("X-Mem-Actor-Id")
}

func (s *Server) keyID(r *http.Request) string {
	return r.Header.Get("X-Mem-Key-Id")
}

func (s *Server) traceID(r *http.Request) string {
	return r.Header.Get("X-Mem-Trace-Id")
}

func (s *Server) logError(r *http.Request, msg string, err error) {
	slog.Error(msg, "error", err, "trace_id", s.traceID(r), "tenant_id", s.tenantID(r))
}
