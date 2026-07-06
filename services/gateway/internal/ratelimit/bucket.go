package ratelimit

import (
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/contexta/gateway/internal/auth"
	"github.com/redis/go-redis/v9"
)

type RateLimiter struct {
	redis *redis.Client
}

func New(rdb *redis.Client) *RateLimiter {
	return &RateLimiter{redis: rdb}
}

var tierLimits = map[string]struct{ RPS, Burst int }{
	"hobby":     {10, 20},
	"solo_pro":  {50, 100},
	"team":      {250, 500},
	"scale":     {1000, 2000},
}

const luaScript = `
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4]) or 1

local window = math.floor(now)
local last = redis.call("GET", key .. ":last")
if not last then
  redis.call("SET", key .. ":last", window)
  redis.call("SET", key .. ":tokens", burst - cost)
  return 1
end

local elapsed = window - tonumber(last)
local tokens = tonumber(redis.call("GET", key .. ":tokens") or burst)
tokens = math.min(burst, tokens + elapsed * rate)

if tokens >= cost then
  redis.call("SET", key .. ":last", window)
  redis.call("SET", key .. ":tokens", tokens - cost)
  return 1
else
  return 0
end
`

func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := auth.APIKeyFromContext(r.Context())
		if key == nil {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}

		tier := strings.ToLower(key.Tier)
		limits, ok := tierLimits[tier]
		if !ok {
			limits = tierLimits["hobby"]
		}

		script := redis.NewScript(luaScript)
		redisKey := "ratelimit:" + key.KeyID
		now := float64(nowMs()) / 1000.0

		allowed, err := script.Run(r.Context(), rl.redis, []string{redisKey}, limits.RPS, limits.Burst, int(now), 1).Int()
		if err != nil {
			slog.Error("rate limit check failed", "error", err, "key_id", key.KeyID)
			http.Error(w, `{"error":"rate limit error"}`, http.StatusInternalServerError)
			return
		}

		if allowed == 0 {
			w.Header().Set("Retry-After", "1")
			http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func nowMs() int64 {
	return time.Now().UnixMilli()
}
