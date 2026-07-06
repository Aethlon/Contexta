package internal

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type Consumer struct {
	pool  *pgxpool.Pool
	redis *redis.Client
}

type MeterEvent struct {
	Event     string    `json:"event"`
	Data      map[string]any `json:"data"`
	Timestamp time.Time `json:"timestamp"`
}

func NewConsumer(pool *pgxpool.Pool, rdb *redis.Client) *Consumer {
	return &Consumer{pool: pool, redis: rdb}
}

func (c *Consumer) Run(ctx context.Context) error {
	groupName := "aggregator"
	consumerName := fmt.Sprintf("worker-%d", time.Now().UnixNano())

	err := c.redis.XGroupCreateMkStream(ctx, "meter:events", groupName, "$").Err()
	if err != nil && err.Error() != "BUSYGROUP Consumer Group name already exists" {
		slog.Warn("xgroup create", "error", err)
	}

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		entries, err := c.redis.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    groupName,
			Consumer: consumerName,
			Streams:  []string{"meter:events", ">"},
			Count:    10,
			Block:    5 * time.Second,
		}).Result()
		if err != nil {
			if err == redis.Nil {
				continue
			}
			slog.Error("xreadgroup error", "error", err)
			time.Sleep(time.Second)
			continue
		}

		for _, stream := range entries {
			for _, msg := range stream.Messages {
				payload, ok := msg.Values["payload"].(string)
				if !ok {
					c.ack(ctx, "meter:events", groupName, msg.ID)
					continue
				}

				var event MeterEvent
				if err := json.Unmarshal([]byte(payload), &event); err != nil {
					slog.Error("failed to unmarshal meter event", "error", err)
					c.ack(ctx, "meter:events", groupName, msg.ID)
					continue
				}

				if err := c.process(ctx, &event); err != nil {
					slog.Error("failed to process event", "error", err, "event", event.Event)
					continue
				}

				c.ack(ctx, "meter:events", groupName, msg.ID)
			}
		}
	}
}

func (c *Consumer) process(ctx context.Context, event *MeterEvent) error {
	tenantID, _ := event.Data["tenant_id"].(string)
	actorID, _ := event.Data["actor_id"].(string)
	eventType := event.Event
	recordedAt := event.Timestamp

	if recordedAt.IsZero() {
		recordedAt = time.Now().UTC()
	}

	_, err := c.pool.Exec(ctx, `
		INSERT INTO usage_event (tenant_id, actor_id, event_type, recorded_at, metadata)
		VALUES ($1, $2, $3, $4, $5)`,
		tenantID, actorID, eventType, recordedAt, []byte("{}"),
	)
	if err != nil {
		return fmt.Errorf("insert usage_event: %w", err)
	}

	return nil
}

func (c *Consumer) ack(ctx context.Context, stream, group, msgID string) {
	if err := c.redis.XAck(ctx, stream, group, msgID).Err(); err != nil {
		slog.Error("failed to ack message", "error", err, "msg_id", msgID)
	}
}
