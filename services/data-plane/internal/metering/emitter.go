package metering

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"
)

type Emitter struct {
	Redis *redis.Client
}

type Event struct {
	Event     string    `json:"event"`
	Data      any       `json:"data"`
	Timestamp time.Time `json:"timestamp"`
}

func (e *Emitter) Emit(ctx context.Context, event string, data any) {
	payload, err := json.Marshal(Event{
		Event:     event,
		Data:      data,
		Timestamp: time.Now().UTC(),
	})
	if err != nil {
		slog.Error("failed to marshal meter event", "error", err)
		return
	}

	if err := e.Redis.XAdd(ctx, &redis.XAddArgs{
		Stream: "meter:events",
		Values: map[string]any{
			"payload": string(payload),
		},
		MaxLen: 100000,
	}).Err(); err != nil {
		slog.Error("failed to emit meter event", "error", err, "event", event)
	}
}
