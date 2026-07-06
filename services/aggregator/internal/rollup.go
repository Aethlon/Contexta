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
		INSERT INTO usage_daily (date, tenant_id, actor_id, event_type, count)
		SELECT
			$1::date AS date,
			tenant_id,
			actor_id,
			event_type,
			COUNT(*) AS count
		FROM usage_event
		WHERE recorded_at >= $1::timestamp
		  AND recorded_at < ($1::date + interval '1 day')
		GROUP BY tenant_id, actor_id, event_type
		ON CONFLICT (date, tenant_id, actor_id, event_type)
		DO UPDATE SET count = EXCLUDED.count,
					  updated_at = now()
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
