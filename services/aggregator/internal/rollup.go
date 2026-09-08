package internal

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Rollup struct {
	pool *pgxpool.Pool
}

func NewRollup(pool *pgxpool.Pool) *Rollup {
	return &Rollup{pool: pool}
}

func (r *Rollup) Run(ctx context.Context) error {
	now := time.Now().UTC()
	today := now.Format("2006-01-02")

	tag, err := r.pool.Exec(ctx, `
		INSERT INTO usage_daily (organization_id, project_id, day, classification, units, bytes_in, bytes_out, llm_tokens_in, llm_tokens_out, request_count, cost_micros)
		SELECT
			organization_id,
			project_id,
			$1::date AS day,
			classification,
			COALESCE(SUM(units), 0) AS units,
			COALESCE(SUM(bytes_in), 0) AS bytes_in,
			COALESCE(SUM(bytes_out), 0) AS bytes_out,
			COALESCE(SUM(llm_tokens_in), 0) AS llm_tokens_in,
			COALESCE(SUM(llm_tokens_out), 0) AS llm_tokens_out,
			COUNT(*) AS request_count,
			0 AS cost_micros
		FROM usage_event
		WHERE occurred_at >= $1::timestamp
		  AND occurred_at < ($1::date + interval '1 day')
		GROUP BY organization_id, project_id, classification
		ON CONFLICT (organization_id, project_id, day, classification)
		DO UPDATE SET
			units = EXCLUDED.units,
			bytes_in = EXCLUDED.bytes_in,
			bytes_out = EXCLUDED.bytes_out,
			llm_tokens_in = EXCLUDED.llm_tokens_in,
			llm_tokens_out = EXCLUDED.llm_tokens_out,
			request_count = EXCLUDED.request_count
	`, today)
	if err != nil {
		return fmt.Errorf("daily rollup: %w", err)
	}

	slog.Info("daily rollup completed",
		"date", today,
		"rows_affected", tag.RowsAffected(),
	)

	return nil
}
