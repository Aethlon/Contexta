package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/contexta/gateway/internal/auth"
	"github.com/contexta/gateway/internal/ratelimit"
	"github.com/contexta/gateway/internal/server"
	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

// redisCache adapts go-redis's command-builder style to the narrow interface the
// retrieval cache needs, so the server package stays free of a Redis dependency.
type redisCache struct{ client *redis.Client }

func (r redisCache) Get(ctx context.Context, key string) (string, error) {
	return r.client.Get(ctx, key).Result()
}

func (r redisCache) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return r.client.Set(ctx, key, value, ttl).Err()
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rdb := redis.NewClient(&redis.Options{
		Addr: os.Getenv("REDIS_ADDR"),
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("failed to connect to redis", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()

	pythonAPIURL := os.Getenv("PYTHON_API_URL")
	if pythonAPIURL == "" {
		pythonAPIURL = "http://localhost:8000"
	}

	verifier := auth.NewVerifier(rdb)
	rl := ratelimit.New(rdb)
	srv := server.New(verifier, rl, pythonAPIURL)

	// Read-path cache. Reads are the dominant cost (embedding + rerank), and recall
	// traffic is highly repetitive, so a short-TTL Redis cache plus single-flight
	// removes a large share of that work before it reaches Python.
	cacheTTL := 30 * time.Second
	if raw := os.Getenv("RETRIEVAL_CACHE_TTL_SECONDS"); raw != "" {
		if seconds, err := strconv.Atoi(raw); err == nil {
			cacheTTL = time.Duration(seconds) * time.Second
		} else {
			slog.Warn("invalid RETRIEVAL_CACHE_TTL_SECONDS, using default", "value", raw)
		}
	}
	if os.Getenv("RETRIEVAL_CACHE_DISABLED") == "" {
		srv.SetCache(redisCache{rdb}, cacheTTL)
		slog.Info("retrieval cache enabled", "ttl", cacheTTL.String())
	} else {
		slog.Info("retrieval cache disabled")
	}

	r := chi.NewRouter()
	srv.RegisterRoutes(r)

	addr := os.Getenv("LISTEN_ADDR")
	if addr == "" {
		addr = ":8443"
	}

	var httpSrv *http.Server

	certFile := os.Getenv("TLS_CERT_FILE")
	keyFile := os.Getenv("TLS_KEY_FILE")

	if certFile != "" && keyFile != "" {
		httpSrv = &http.Server{
			Addr:         addr,
			Handler:      r,
			ReadTimeout:  10 * time.Second,
			WriteTimeout: 30 * time.Second,
			IdleTimeout:  60 * time.Second,
		}

		shutdown := make(chan os.Signal, 1)
		signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

		go func() {
			slog.Info("gateway listening with TLS", "addr", addr)
			if err := httpSrv.ListenAndServeTLS(certFile, keyFile); err != nil && err != http.ErrServerClosed {
				slog.Error("server error", "error", err)
				os.Exit(1)
			}
		}()

		<-shutdown
	} else {
		httpSrv = &http.Server{
			Addr:         addr,
			Handler:      r,
			ReadTimeout:  10 * time.Second,
			WriteTimeout: 30 * time.Second,
			IdleTimeout:  60 * time.Second,
		}

		shutdown := make(chan os.Signal, 1)
		signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

		go func() {
			slog.Info("gateway listening", "addr", addr)
			if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				slog.Error("server error", "error", err)
				os.Exit(1)
			}
		}()

		<-shutdown
	}

	slog.Info("shutting down")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutdownCancel()

	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		slog.Error("forced shutdown", "error", err)
	}
}
