package auth

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"log/slog"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

type contextKey string

const apiKeyContextKey contextKey = "api_key"

type APIKey struct {
	KeyID    string
	TenantID string
	ActorID  string
	Scopes   string
	Tier     string
}

func (k *APIKey) HasScope(scope string) bool {
	return strings.Contains(k.Scopes, scope)
}

type Verifier struct {
	redis  *redis.Client
	cache  *sync.Map
	cacheW *sync.Map
}

func NewVerifier(rdb *redis.Client) *Verifier {
	return &Verifier{
		redis:  rdb,
		cache:  &sync.Map{},
		cacheW: &sync.Map{},
	}
}

func (v *Verifier) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		apiKey := r.Header.Get("X-API-Key")
		if apiKey == "" {
			apiKey = r.Header.Get("Authorization")
			if strings.HasPrefix(apiKey, "Bearer ") {
				apiKey = strings.TrimPrefix(apiKey, "Bearer ")
			}
		}

		if apiKey == "" {
			writeAuthError(w, http.StatusUnauthorized, "missing API key")
			return
		}

		hash := sha256.Sum256([]byte(apiKey))
		keyHash := hex.EncodeToString(hash[:])

		if cached, ok := v.cache.Load(keyHash); ok {
			key := cached.(*APIKey)
			ctx := context.WithValue(r.Context(), apiKeyContextKey, key)
			next.ServeHTTP(w, r.WithContext(ctx))
			return
		}

		key, err := v.verify(context.Background(), keyHash)
		if err != nil {
			slog.Warn("api key verification failed", "error", err)
			v.cacheW.Store(keyHash, time.Now())
			writeAuthError(w, http.StatusUnauthorized, "invalid API key")
			return
		}

		v.cache.Store(keyHash, key)
		ctx := context.WithValue(r.Context(), apiKeyContextKey, key)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (v *Verifier) verify(ctx context.Context, keyHash string) (*APIKey, error) {
	key := "apikey:" + keyHash
	exists, err := v.redis.Exists(ctx, key).Result()
	if err != nil {
		return nil, err
	}
	if exists == 0 {
		return nil, ErrKeyNotFound
	}

	data, err := v.redis.HGetAll(ctx, key).Result()
	if err != nil {
		return nil, err
	}

	return &APIKey{
		KeyID:    data["key_id"],
		TenantID: data["tenant_id"],
		ActorID:  data["actor_id"],
		Scopes:   data["scopes"],
		Tier:     data["tier"],
	}, nil
}

func APIKeyFromContext(ctx context.Context) *APIKey {
	key, _ := ctx.Value(apiKeyContextKey).(*APIKey)
	return key
}

var ErrKeyNotFound = &authError{"key not found"}

type authError struct{ msg string }

func (e *authError) Error() string { return e.msg }

func writeAuthError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	w.Write([]byte(`{"error":"` + msg + `"}`))
}
