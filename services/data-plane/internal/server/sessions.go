package server

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/contexta/data-plane/internal/storage"
)

type createSessionRequest struct {
	Model    string `json:"model"`
	Provider string `json:"provider"`
}

type sessionResponse struct {
	ID        string    `json:"id"`
	CreatedAt time.Time `json:"created_at"`
}

type endSessionResponse struct {
	ID       string    `json:"id"`
	EndedAt  time.Time `json:"ended_at"`
}

type inspectSession struct {
	ID        string    `json:"id"`
	Model     string    `json:"model"`
	Provider  string    `json:"provider"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	EndedAt   time.Time `json:"ended_at,omitempty"`
}

func (s *Server) CreateSession(w http.ResponseWriter, r *http.Request) {
	var req createSessionRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	tenantID := s.tenantID(r)
	actorID := s.actorID(r)

	sessionID, err := uuid.NewV7()
	if err != nil {
		s.logError(r, "failed to generate session id", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}
	id := sessionID.String()

	session := &storage.Session{
		ID:       id,
		TenantID: tenantID,
		ActorID:  actorID,
		Model:    req.Model,
		Provider: req.Provider,
		Status:   "active",
	}

	if err := s.Store.InsertSession(r.Context(), session); err != nil {
		s.logError(r, "failed to create session", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	slog.Info("session created", "id", id, "tenant_id", tenantID, "actor_id", actorID)

	writeJSON(w, http.StatusCreated, sessionResponse{
		ID:        id,
		CreatedAt: time.Now().UTC(),
	})
}

func (s *Server) EndSession(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	tenantID := s.tenantID(r)

	endedAt := time.Now().UTC()

	if err := s.Store.EndSession(r.Context(), id, tenantID, endedAt); err != nil {
		s.logError(r, "failed to end session", err)
		writeError(w, http.StatusNotFound, "session not found")
		return
	}

	slog.Info("session ended", "id", id, "tenant_id", tenantID)

	writeJSON(w, http.StatusOK, endSessionResponse{
		ID:      id,
		EndedAt: endedAt,
	})
}

func (s *Server) InspectSessions(w http.ResponseWriter, r *http.Request) {
	userID := chi.URLParam(r, "user_id")
	tenantID := s.tenantID(r)

	sessions, err := s.Store.ListSessions(r.Context(), tenantID, userID)
	if err != nil {
		s.logError(r, "failed to list sessions", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	results := make([]inspectSession, 0, len(sessions))
	for _, sess := range sessions {
		results = append(results, inspectSession{
			ID:        sess.ID,
			Model:     sess.Model,
			Provider:  sess.Provider,
			Status:    sess.Status,
			CreatedAt: sess.CreatedAt,
			EndedAt:   sess.EndedAt,
		})
	}

	writeJSON(w, http.StatusOK, results)
}
