package server

import (
	"log/slog"
	"net/http"
	"time"
)

type retrieveRequest struct {
	Query     string    `json:"query"`
	Embedding []float32 `json:"embedding,omitempty"`
	Limit     int       `json:"limit,omitempty"`
	Threshold float64   `json:"threshold,omitempty"`
	Source    string    `json:"source,omitempty"`
	Type      string    `json:"type,omitempty"`
	Tags      []string  `json:"tags,omitempty"`
	StartTime time.Time `json:"start_time,omitempty"`
	EndTime   time.Time `json:"end_time,omitempty"`
}

type memoryResult struct {
	ID        string         `json:"id"`
	Content   string         `json:"content"`
	Source    string         `json:"source"`
	Type      string         `json:"type"`
	Metadata  map[string]any `json:"metadata,omitempty"`
	Tags      []string       `json:"tags,omitempty"`
	Score     float64        `json:"score"`
	CreatedAt time.Time      `json:"created_at"`
}

type retrieveResponse struct {
	Results []memoryResult `json:"results"`
	Total   int            `json:"total"`
}

func (s *Server) Retrieve(w http.ResponseWriter, r *http.Request) {
	var req retrieveRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Limit <= 0 || req.Limit > 100 {
		req.Limit = 20
	}

	tenantID := s.tenantID(r)

	results, err := s.Store.HybridSearch(r.Context(), tenantID, req.Query, req.Embedding, req.Limit, req.Threshold, req.Source, req.Type, req.Tags, req.StartTime, req.EndTime)
	if err != nil {
		s.logError(r, "hybrid search failed", err)
		writeError(w, http.StatusInternalServerError, "search failed")
		return
	}

	resp := retrieveResponse{
		Results: make([]memoryResult, 0, len(results)),
		Total:   len(results),
	}

	for _, obs := range results {
		resp.Results = append(resp.Results, memoryResult{
			ID:        obs.ID,
			Content:   obs.Content,
			Source:    obs.Source,
			Type:      obs.Type,
			Metadata:  obs.Metadata,
			Tags:      obs.Tags,
			Score:     obs.Score,
			CreatedAt: obs.CreatedAt,
		})
	}

	slog.Info("retrieval completed",
		"tenant_id", tenantID,
		"results", len(results),
		"query_length", len(req.Query),
	)

	writeJSON(w, http.StatusOK, resp)
}
