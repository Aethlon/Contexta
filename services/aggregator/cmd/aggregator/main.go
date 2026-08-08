package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/contexta/aggregator/internal"
	"github.com/redis/go-redis/v9"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pgPool, err := pgxpool.New(ctx, os.Getenv("DATABASE_URL"))
	if err != nil {
		slog.Error("failed to connect to postgres", "error", err)
		os.Exit(1)
	}
	defer pgPool.Close()

	rdb := redis.NewClient(&redis.Options{
		Addr: os.Getenv("REDIS_ADDR"),
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("failed to connect to redis", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()

	consumer := internal.NewConsumer(pgPool, rdb)
	rollup := internal.NewRollup(pgPool)

	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

	ctx, stop := context.WithCancel(context.Background())
	defer stop()

	go func() {
		slog.Info("starting meter event consumer")
		if err := consumer.Run(ctx); err != nil && err != context.Canceled {
			slog.Error("consumer error", "error", err)
		}
	}()

	go func() {
		slog.Info("starting daily rollup")
		ticker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := rollup.Run(ctx); err != nil {
					slog.Error("rollup error", "error", err)
				}
			}
		}
	}()

	<-shutdown
	slog.Info("shutting down aggregator")
	stop()
}
