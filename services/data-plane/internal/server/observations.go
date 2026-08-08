package server

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/contexta/data-plane/internal/storage"
)

type ingestRequest struct {
	Content   string            `json:"content"`
	Source    string            `json:"source"`
	Type      string            `json:"type"`
	Metadata  map[string]any    `json:"metadata,omitempty"`
	Embedding []float32         `json:"embedding,omitempty"`
	Tags      []string          `json:"tags,omitempty"`
}

type ingestResponse struct {
	ID        string    `json:"id"`
	Redacted  bool      `json:"redacted"`
	CreatedAt time.Time `json:"created_at"`
}

func decodeBody(r *http.Request, v any) error {
	defer r.Body.Close()
	return json.NewDecoder(r.Body).Decode(v)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func (s *Server) IngestObservation(w http.ResponseWriter, r *http.Request) {
	var req ingestRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	idempotencyKey := r.Header.Get("Idempotency-Key")
	tenantID := s.tenantID(r)
	actorID := s.actorID(r)

	obsID, err := uuid.NewV7()
	if err != nil {
		s.logError(r, "failed to generate id", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}
	id := obsID.String()

	_, changed := s.Filter.Apply(&req.Content)

	obs := &storage.Observation{
		ID:             id,
		TenantID:       tenantID,
		ActorID:        actorID,
		Content:        req.Content,
		Source:         req.Source,
		Type:           req.Type,
		Metadata:       req.Metadata,
		Embedding:      req.Embedding,
		Tags:           req.Tags,
		Redacted:       changed,
		IdempotencyKey: idempotencyKey,
	}

	if err := s.Store.InsertObservation(r.Context(), obs); err != nil {
		s.logError(r, "failed to insert observation", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	s.Emitter.Emit(r.Context(), "observation:created", map[string]any{
		"id":        id,
		"tenant_id": tenantID,
		"actor_id":  actorID,
		"type":      req.Type,
		"redacted":  changed,
		"source":    req.Source,
		"timestamp": time.Now().UTC(),
	})

	slog.Info("observation ingested",
		"id", id,
		"tenant_id", tenantID,
		"redacted", changed,
	)

	writeJSON(w, http.StatusCreated, ingestResponse{
		ID:        id,
		Redacted:  changed,
		CreatedAt: time.Now().UTC(),
	})
}

func (s *Server) IngestBatch(w http.ResponseWriter, r *http.Request) {
	var reqs []ingestRequest
	if err := decodeBody(r, &reqs); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if len(reqs) > 100 {
		writeError(w, http.StatusBadRequest, "batch limit is 100")
		return
	}

	tenantID := s.tenantID(r)
	actorID := s.actorID(r)
	results := make([]ingestResponse, 0, len(reqs))

	for _, req := range reqs {
		obsID, err := uuid.NewV7()
		if err != nil {
			s.logError(r, "failed to generate id", err)
			continue
		}
		id := obsID.String()

		_, changed := s.Filter.Apply(&req.Content)

		obs := &storage.Observation{
			ID:        id,
			TenantID:  tenantID,
			ActorID:   actorID,
			Content:   req.Content,
			Source:    req.Source,
			Type:      req.Type,
			Metadata:  req.Metadata,
			Embedding: req.Embedding,
			Tags:      req.Tags,
			Redacted:  changed,
		}

		if err := s.Store.InsertObservation(r.Context(), obs); err != nil {
			s.logError(r, "failed to insert observation", err)
			continue
		}

		results = append(results, ingestResponse{
			ID:        id,
			Redacted:  changed,
			CreatedAt: time.Now().UTC(),
		})
	}

	s.Emitter.Emit(r.Context(), "observation:batch", map[string]any{
		"count":     len(results),
		"tenant_id": tenantID,
		"actor_id":  actorID,
	})

	writeJSON(w, http.StatusCreated, results)
}
