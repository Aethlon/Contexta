package router

import (
	"github.com/go-chi/chi/v5"
	"github.com/contexta/gateway/internal/auth"
	"github.com/contexta/gateway/internal/ratelimit"
	"github.com/contexta/gateway/internal/server"
)

type Config struct {
	DataPlaneURL string
	PythonAPIURL string
	Verifier     *auth.Verifier
	RateLimiter  *ratelimit.RateLimiter
}

func Build(cfg *Config) chi.Router {
	r := chi.NewRouter()
	srv := server.New(cfg.Verifier, cfg.RateLimiter, cfg.DataPlaneURL, cfg.PythonAPIURL)
	srv.RegisterRoutes(r)
	return r
}
