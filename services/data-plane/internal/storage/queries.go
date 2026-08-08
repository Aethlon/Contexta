package storage

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type Store struct {
	Pool  *pgxpool.Pool
	Redis *redis.Client
}

type Observation struct {
	ID             string         `json:"id"`
	TenantID       string         `json:"tenant_id"`
	ActorID        string         `json:"actor_id"`
	Content        string         `json:"content"`
	Source         string         `json:"source"`
	Type           string         `json:"type"`
	Metadata       map[string]any `json:"metadata,omitempty"`
	Embedding      []float32      `json:"embedding,omitempty"`
	Tags           []string       `json:"tags,omitempty"`
	Status         string         `json:"status"`
	Pinned         bool           `json:"pinned"`
	Redacted       bool           `json:"redacted"`
	IdempotencyKey string         `json:"idempotency_key,omitempty"`
	Score          float64        `json:"score"`
	CreatedAt      time.Time      `json:"created_at"`
	UpdatedAt      time.Time      `json:"updated_at"`
}

type Session struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	ActorID   string    `json:"actor_id"`
	Model     string    `json:"model"`
	Provider  string    `json:"provider"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	EndedAt   time.Time `json:"ended_at"`
}

func (s *Store) InsertObservation(ctx context.Context, obs *Observation) error {
	if obs.IdempotencyKey != "" {
		key := fmt.Sprintf("idempotent:obs:%s", obs.IdempotencyKey)
		exists, err := s.Redis.SetNX(ctx, key, obs.ID, 24*time.Hour).Result()
		if err != nil {
			return fmt.Errorf("idempotency check failed: %w", err)
		}
		if !exists {
			return nil
		}
	}

	metadataJSON := []byte("{}")
	if obs.Metadata != nil {
		var err error
		metadataJSON, err = jsonMarshal(obs.Metadata)
		if err != nil {
			return fmt.Errorf("metadata marshal: %w", err)
		}
	}

	tagsJSON := []byte("[]")
	if len(obs.Tags) > 0 {
		var err error
		tagsJSON, err = jsonMarshal(obs.Tags)
		if err != nil {
			return fmt.Errorf("tags marshal: %w", err)
		}
	}

	_, err := s.Pool.Exec(ctx, `
		INSERT INTO observations (id, tenant_id, actor_id, content, source, type, metadata, embedding, tags, redacted)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		ON CONFLICT (id) DO NOTHING`,
		obs.ID, obs.TenantID, obs.ActorID, obs.Content, obs.Source, obs.Type,
		metadataJSON, obs.Embedding, tagsJSON, obs.Redacted,
	)
	if err != nil {
		return fmt.Errorf("insert observation: %w", err)
	}

	return nil
}

func (s *Store) GetObservation(ctx context.Context, id, tenantID string) (*Observation, error) {
	obs := &Observation{}
	err := s.Pool.QueryRow(ctx, `
		SELECT id, tenant_id, actor_id, content, source, type, metadata, embedding, tags, status, pinned, redacted, created_at, updated_at
		FROM observations WHERE id = $1 AND tenant_id = $2`, id, tenantID).Scan(
		&obs.ID, &obs.TenantID, &obs.ActorID, &obs.Content, &obs.Source, &obs.Type,
		&obs.Metadata, &obs.Embedding, &obs.Tags, &obs.Status, &obs.Pinned,
		&obs.Redacted, &obs.CreatedAt, &obs.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("get observation: %w", err)
	}
	return obs, nil
}

func (s *Store) UpdateLifecycle(ctx context.Context, id, tenantID, action string) error {
	switch action {
	case "pin":
		_, err := s.Pool.Exec(ctx, `UPDATE observations SET pinned = true, updated_at = now() WHERE id = $1 AND tenant_id = $2`, id, tenantID)
		return err
	case "unpin":
		_, err := s.Pool.Exec(ctx, `UPDATE observations SET pinned = false, updated_at = now() WHERE id = $1 AND tenant_id = $2`, id, tenantID)
		return err
	case "archive":
		_, err := s.Pool.Exec(ctx, `UPDATE observations SET status = 'archived', updated_at = now() WHERE id = $1 AND tenant_id = $2`, id, tenantID)
		return err
	case "restore":
		_, err := s.Pool.Exec(ctx, `UPDATE observations SET status = 'active', updated_at = now() WHERE id = $1 AND tenant_id = $2`, id, tenantID)
		return err
	default:
		return fmt.Errorf("unknown lifecycle action: %s", action)
	}
}

func (s *Store) HardDelete(ctx context.Context, id, tenantID string) error {
	result, err := s.Pool.Exec(ctx, `DELETE FROM observations WHERE id = $1 AND tenant_id = $2`, id, tenantID)
	if err != nil {
		return err
	}
	if result.RowsAffected() == 0 {
		return fmt.Errorf("observation not found")
	}
	return nil
}

func (s *Store) HybridSearch(ctx context.Context, tenantID, query string, embedding []float32, limit int, threshold float64, source, obsType string, tags []string, startTime, endTime time.Time) ([]Observation, error) {
	var conditions []string
	var args []any
	argIdx := 1

	conditions = append(conditions, fmt.Sprintf("tenant_id = $%d", argIdx))
	args = append(args, tenantID)
	argIdx++

	conditions = append(conditions, fmt.Sprintf("status = 'active'"))

	if query != "" {
		conditions = append(conditions, fmt.Sprintf("to_tsvector('english', content) @@ plainto_tsquery('english', $%d)", argIdx))
		args = append(args, query)
		argIdx++
	}

	if source != "" {
		conditions = append(conditions, fmt.Sprintf("source = $%d", argIdx))
		args = append(args, source)
		argIdx++
	}

	if obsType != "" {
		conditions = append(conditions, fmt.Sprintf("type = $%d", argIdx))
		args = append(args, obsType)
		argIdx++
	}

	if len(tags) > 0 {
		conditions = append(conditions, fmt.Sprintf("tags ?| $%d", argIdx))
		args = append(args, tags)
		argIdx++
	}

	if !startTime.IsZero() {
		conditions = append(conditions, fmt.Sprintf("created_at >= $%d", argIdx))
		args = append(args, startTime)
		argIdx++
	}

	if !endTime.IsZero() {
		conditions = append(conditions, fmt.Sprintf("created_at <= $%d", argIdx))
		args = append(args, endTime)
		argIdx++
	}

	whereClause := strings.Join(conditions, " AND ")

	var selectClause string
	if len(embedding) > 0 {
		selectClause = fmt.Sprintf(`
			SELECT id, tenant_id, actor_id, content, source, type, metadata, embedding, tags, status, pinned, redacted, created_at, updated_at,
				1 - (embedding <=> $%d::vector) AS score
			FROM observations
			WHERE %s AND embedding IS NOT NULL
			ORDER BY score DESC
			LIMIT $%d`, argIdx, whereClause, argIdx+1)
		args = append(args, embedding, limit)
	} else {
		selectClause = fmt.Sprintf(`
			SELECT id, tenant_id, actor_id, content, source, type, metadata, embedding, tags, status, pinned, redacted, created_at, updated_at,
				ts_rank(to_tsvector('english', content), plainto_tsquery('english', $%d)) AS score
			FROM observations
			WHERE %s
			ORDER BY score DESC
			LIMIT $%d`, argIdx-1, whereClause, argIdx)
		conditions = append(conditions, fmt.Sprintf("LIMIT $%d", argIdx))
		args = append(args, limit)
		argIdx++
	}

	rows, err := s.Pool.Query(ctx, selectClause, args...)
	if err != nil {
		return nil, fmt.Errorf("hybrid search: %w", err)
	}
	defer rows.Close()

	var results []Observation
	for rows.Next() {
		var obs Observation
		if err := rows.Scan(
			&obs.ID, &obs.TenantID, &obs.ActorID, &obs.Content, &obs.Source, &obs.Type,
			&obs.Metadata, &obs.Embedding, &obs.Tags, &obs.Status, &obs.Pinned,
			&obs.Redacted, &obs.CreatedAt, &obs.UpdatedAt, &obs.Score,
		); err != nil {
			return nil, fmt.Errorf("scan observation: %w", err)
		}
		if threshold > 0 && obs.Score < threshold {
			continue
		}
		results = append(results, obs)
	}

	return results, nil
}

func (s *Store) InsertSession(ctx context.Context, session *Session) error {
	_, err := s.Pool.Exec(ctx, `
		INSERT INTO sessions (id, tenant_id, actor_id, model, provider, status)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		session.ID, session.TenantID, session.ActorID, session.Model, session.Provider, session.Status,
	)
	return err
}

func (s *Store) EndSession(ctx context.Context, id, tenantID string, endedAt time.Time) error {
	result, err := s.Pool.Exec(ctx, `
		UPDATE sessions SET status = 'ended', ended_at = $3 WHERE id = $1 AND tenant_id = $2 AND status = 'active'`,
		id, tenantID, endedAt,
	)
	if err != nil {
		return err
	}
	if result.RowsAffected() == 0 {
		return fmt.Errorf("active session not found")
	}
	return nil
}

func (s *Store) ListSessions(ctx context.Context, tenantID, actorID string) ([]Session, error) {
	rows, err := s.Pool.Query(ctx, `
		SELECT id, tenant_id, actor_id, model, provider, status, created_at, COALESCE(ended_at, '0001-01-01T00:00:00Z'::timestamp) as ended_at
		FROM sessions
		WHERE tenant_id = $1 AND actor_id = $2
		ORDER BY created_at DESC
		LIMIT 100`, tenantID, actorID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var sessions []Session
	for rows.Next() {
		var s Session
		if err := rows.Scan(&s.ID, &s.TenantID, &s.ActorID, &s.Model, &s.Provider, &s.Status, &s.CreatedAt, &s.EndedAt); err != nil {
			return nil, err
		}
		sessions = append(sessions, s)
	}
	return sessions, nil
}

func jsonMarshal(v any) ([]byte, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("json marshal: %w", err)
	}
	return b, nil
}


