package server

import (
	"log/slog"
	"net/http"
	"time"
)

type contextRequest struct {
	Query       string    `json:"query"`
	Embedding   []float32 `json:"embedding,omitempty"`
	Limit       int       `json:"limit,omitempty"`
	MaxTokens   int       `json:"max_tokens,omitempty"`
	Source      string    `json:"source,omitempty"`
	Type        string    `json:"type,omitempty"`
	Tags        []string  `json:"tags,omitempty"`
	StartTime   time.Time `json:"start_time,omitempty"`
	EndTime     time.Time `json:"end_time,omitempty"`
}

type contextMemory struct {
	ID        string         `json:"id"`
	Content   string         `json:"content"`
	Source    string         `json:"source"`
	Type      string         `json:"type"`
	Metadata  map[string]any `json:"metadata,omitempty"`
	Score     float64        `json:"score"`
	CreatedAt time.Time      `json:"created_at"`
}

type contextResponse struct {
	Memories  []contextMemory `json:"memories"`
	Total     int             `json:"total"`
	Truncated bool            `json:"truncated"`
}

func (s *Server) Context(w http.ResponseWriter, r *http.Request) {
	var req contextRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Limit <= 0 || req.Limit > 50 {
		req.Limit = 20
	}
	if req.MaxTokens <= 0 {
		req.MaxTokens = 4000
	}

	tenantID := s.tenantID(r)

	results, err := s.Store.HybridSearch(r.Context(), tenantID, req.Query, req.Embedding, req.Limit, 0.0, req.Source, req.Type, req.Tags, req.StartTime, req.EndTime)
	if err != nil {
		s.logError(r, "context search failed", err)
		writeError(w, http.StatusInternalServerError, "search failed")
		return
	}

	totalTokens := 0
	truncated := false
	memories := make([]contextMemory, 0, len(results))

	for _, obs := range results {
		tokens := len(obs.Content) / 4
		if totalTokens+tokens > req.MaxTokens {
			truncated = true
			break
		}
		totalTokens += tokens
		memories = append(memories, contextMemory{
			ID:        obs.ID,
			Content:   obs.Content,
			Source:    obs.Source,
			Type:      obs.Type,
			Metadata:  obs.Metadata,
			Score:     obs.Score,
			CreatedAt: obs.CreatedAt,
		})
	}

	slog.Info("context bundle built",
		"tenant_id", tenantID,
		"memories", len(memories),
		"total_tokens", totalTokens,
		"truncated", truncated,
	)

	writeJSON(w, http.StatusOK, contextResponse{
		Memories:  memories,
		Total:     len(memories),
		Truncated: truncated,
	})
}
