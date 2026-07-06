package server

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

type memoryResponse struct {
	ID        string         `json:"id"`
	Content   string         `json:"content"`
	Source    string         `json:"source"`
	Type      string         `json:"type"`
	Metadata  map[string]any `json:"metadata,omitempty"`
	Tags      []string       `json:"tags,omitempty"`
	Status    string         `json:"status"`
	Pinned    bool           `json:"pinned"`
	CreatedAt time.Time      `json:"created_at"`
	UpdatedAt time.Time      `json:"updated_at"`
}

func (s *Server) GetMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	obs, err := s.Store.GetObservation(r.Context(), id, tenantID)
	if err != nil {
		s.logError(r, "memory not found", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	writeJSON(w, http.StatusOK, memoryResponse{
		ID:        obs.ID,
		Content:   obs.Content,
		Source:    obs.Source,
		Type:      obs.Type,
		Metadata:  obs.Metadata,
		Tags:      obs.Tags,
		Status:    obs.Status,
		Pinned:    obs.Pinned,
		CreatedAt: obs.CreatedAt,
		UpdatedAt: obs.UpdatedAt,
	})
}

func (s *Server) PinMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	if err := s.Store.UpdateLifecycle(r.Context(), id, tenantID, "pin"); err != nil {
		s.logError(r, "pin failed", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	s.Emitter.Emit(r.Context(), "memory:pin", map[string]any{
		"id": id, "tenant_id": tenantID,
	})

	slog.Info("memory pinned", "id", id, "tenant_id", tenantID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "pinned"})
}

func (s *Server) UnpinMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	if err := s.Store.UpdateLifecycle(r.Context(), id, tenantID, "unpin"); err != nil {
		s.logError(r, "unpin failed", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	s.Emitter.Emit(r.Context(), "memory:unpin", map[string]any{
		"id": id, "tenant_id": tenantID,
	})

	slog.Info("memory unpinned", "id", id, "tenant_id", tenantID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "unpinned"})
}

func (s *Server) ArchiveMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	if err := s.Store.UpdateLifecycle(r.Context(), id, tenantID, "archive"); err != nil {
		s.logError(r, "archive failed", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	s.Emitter.Emit(r.Context(), "memory:archive", map[string]any{
		"id": id, "tenant_id": tenantID,
	})

	slog.Info("memory archived", "id", id, "tenant_id", tenantID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "archived"})
}

func (s *Server) RestoreMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	if err := s.Store.UpdateLifecycle(r.Context(), id, tenantID, "restore"); err != nil {
		s.logError(r, "restore failed", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	s.Emitter.Emit(r.Context(), "memory:restore", map[string]any{
		"id": id, "tenant_id": tenantID,
	})

	slog.Info("memory restored", "id", id, "tenant_id", tenantID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "restored"})
}

func (s *Server) DeleteMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	if err := s.Store.HardDelete(r.Context(), id, tenantID); err != nil {
		s.logError(r, "delete failed", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	s.Emitter.Emit(r.Context(), "memory:delete", map[string]any{
		"id": id, "tenant_id": tenantID,
	})

	slog.Info("memory deleted", "id", id, "tenant_id", tenantID)
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) ExplainMemory(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	obs, err := s.Store.GetObservation(r.Context(), id, tenantID)
	if err != nil {
		s.logError(r, "memory not found", err)
		writeError(w, http.StatusNotFound, "memory not found")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"id":          obs.ID,
		"content":     obs.Content,
		"explanation": "explainability is routed to the Python explainability service",
		"note":        "call /api/v1/explain on the Python API for full details",
	})
}
