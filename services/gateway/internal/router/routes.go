package router

import (
	"github.com/contexta/gateway/internal/auth"
	"github.com/contexta/gateway/internal/ratelimit"
	"github.com/contexta/gateway/internal/server"
	"github.com/go-chi/chi/v5"
)

type Config struct {
	PythonAPIURL string
	Verifier     *auth.Verifier
	RateLimiter  *ratelimit.RateLimiter
}

func Build(cfg *Config) chi.Router {
	r := chi.NewRouter()
	srv := server.New(cfg.Verifier, cfg.RateLimiter, cfg.PythonAPIURL)
	srv.RegisterRoutes(r)
	return r
}
