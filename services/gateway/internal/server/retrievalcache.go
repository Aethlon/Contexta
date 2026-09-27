package server

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

// RetrievalCache adds two read-path optimisations in front of the Python API:
//
//  1. Response cache - identical retrieval queries inside a short TTL are served
//     from Redis without touching Python at all. Memory recall is extremely
//     repetitive (agents re-ask the same question while iterating), so this
//     removes a meaningful share of embedding + rerank work.
//
//  2. Single-flight - concurrent identical queries collapse into one upstream
//     request, so a burst of N identical asks costs one embedding call instead of N.
//
// The cache key includes the tenant, the user, the full request body and the API
// key identity, so a cached response can never cross a tenant boundary. Only GET
// and POST bodies are buffered, and only for paths on the allowlist below.
type RetrievalCache struct {
	redis    RedisClient
	ttl      time.Duration
	inflight sync.Map // key -> *flight
}

// flight is one shared upstream request that concurrent duplicates wait on.
type flight struct {
	done   chan struct{}
	status int
	body   []byte
	header http.Header
	err    error
}

// RedisClient is the subset of go-redis this package needs, so the concrete
// client stays an implementation detail and the cache is testable without Redis.
type RedisClient interface {
	Get(ctx context.Context, key string) (string, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
}

// cacheablePaths are the read endpoints worth caching. Writes are never cached.
var cacheablePaths = map[string]time.Duration{
	"/v1/retrieve":             30 * time.Second,
	"/api/v1/retrieve":         30 * time.Second,
	"/v1/memories/context":     30 * time.Second,
	"/api/v1/memories/context": 30 * time.Second,
	"/v1/memories/search":      30 * time.Second,
	"/api/v1/memories/search":  30 * time.Second,
	"/v1/retrieve/batch":       30 * time.Second,
	"/api/v1/retrieve/batch":   30 * time.Second,
}

const maxCacheBodyBytes = 4 << 20 // 4 MiB

// Cacheable reports whether a path participates in the response cache.
func cacheablePath(path string) (time.Duration, bool) {
	ttl, ok := cacheablePaths[path]
	return ttl, ok
}

func (c *RetrievalCache) cacheKey(r *http.Request, body []byte) string {
	tenant := firstNonEmpty(
		r.Header.Get("X-Organization-Id"),
		r.Header.Get("X-Org-Id"),
		r.Header.Get("X-Mem-Tenant-Id"),
	)
	user := firstNonEmpty(
		r.Header.Get("X-User-Id"),
		r.Header.Get("X-Contexta-User-Id"),
		r.Header.Get("X-Mem-Actor-Id"),
	)
	// The API key identity is part of the key so two keys for different actors in
	// the same tenant cannot observe each other's cached results.
	apiKey := r.Header.Get("X-Api-Key")

	sum := sha256.New()
	sum.Write([]byte(r.Method))
	sum.Write([]byte("\x00"))
	sum.Write([]byte(r.URL.RequestURI()))
	sum.Write([]byte("\x00"))
	sum.Write([]byte(tenant))
	sum.Write([]byte("\x00"))
	sum.Write([]byte(user))
	sum.Write([]byte("\x00"))
	sum.Write([]byte(apiKey))
	sum.Write([]byte("\x00"))
	sum.Write(body)
	return "rq:" + hex.EncodeToString(sum.Sum(nil))[:32]
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

type cachedResponse struct {
	Status int `json:"status"`
	// Header preserves Content-Encoding, so a gzipped upstream body is replayed
	// with its encoding intact.
	Header map[string]string `json:"header"`
	// Body is []byte rather than json.RawMessage: the upstream may gzip the
	// response, and compressed bytes are not valid JSON. Go encodes []byte as
	// base64, so this round-trips any payload.
	Body []byte `json:"body"`
}

func (c *RetrievalCache) get(ctx context.Context, key string) (*cachedResponse, bool) {
	if c == nil || c.redis == nil {
		return nil, false
	}
	raw, err := c.redis.Get(ctx, key)
	if err != nil || raw == "" {
		return nil, false
	}
	var entry cachedResponse
	if err := json.Unmarshal([]byte(raw), &entry); err != nil {
		return nil, false
	}
	return &entry, true
}

func (c *RetrievalCache) set(ctx context.Context, key string, entry *cachedResponse, ttl time.Duration) {
	if c == nil || c.redis == nil {
		return
	}
	raw, err := json.Marshal(entry)
	if err != nil {
		slog.Warn("retrieval cache marshal failed", "error", err)
		return
	}
	if err := c.redis.Set(ctx, key, string(raw), ttl); err != nil {
		slog.Warn("retrieval cache write failed", "error", err, "key", key)
	}
}

// CachedProxy wraps a handler with the response cache and single-flight. It
// degrades to a plain proxy whenever Redis is unavailable.
func CachedProxy(next http.Handler, cache *RetrievalCache) http.Handler {
	if cache == nil || cache.redis == nil {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ttl, ok := cacheablePath(r.URL.Path)
		if !ok || (r.Method != http.MethodPost && r.Method != http.MethodGet) {
			next.ServeHTTP(w, r)
			return
		}

		var body []byte
		if r.Body != nil {
			read, err := io.ReadAll(io.LimitReader(r.Body, maxCacheBodyBytes))
			if err != nil {
				next.ServeHTTP(w, r)
				return
			}
			body = read
			r.Body = io.NopCloser(bytes.NewReader(body))
		}

		key := cache.cacheKey(r, body)
		ctx := r.Context()

		if entry, hit := cache.get(ctx, key); hit {
			w.Header().Set("X-Contexta-Cache", "hit")
			for name, value := range entry.Header {
				w.Header().Set(name, value)
			}
			w.WriteHeader(entry.Status)
			_, _ = w.Write(entry.Body)
			return
		}

		// Single-flight: the first caller performs the upstream request, the rest
		// wait for its result instead of stampeding the model server. The flight
		// stored in the map must be the same object the leader completes, otherwise
		// waiters block on a channel that is never closed.
		stored, loaded := cache.inflight.LoadOrStore(key, &flight{done: make(chan struct{})})
		f := stored.(*flight)

		if loaded {
			select {
			case <-f.done:
				if f.err != nil {
					next.ServeHTTP(w, r)
					return
				}
				w.Header().Set("X-Contexta-Cache", "coalesced")
				for name, values := range f.header {
					for _, value := range values {
						w.Header().Add(name, value)
					}
				}
				w.WriteHeader(f.status)
				_, _ = w.Write(f.body)
			case <-ctx.Done():
				// The leader is slow or gone; fall through to an independent call
				// rather than holding this request open indefinitely.
				next.ServeHTTP(w, r)
			}
			return
		}

		rec := &responseRecorder{header: http.Header{}}
		next.ServeHTTP(rec, r)

		f.status = rec.status
		f.body = rec.body
		f.header = rec.header
		if rec.status >= 200 && rec.status < 300 && len(rec.body) > 0 {
			entry := &cachedResponse{Status: rec.status, Body: rec.body, Header: map[string]string{}}
			for name, values := range rec.header {
				if len(values) > 0 {
					entry.Header[name] = values[0]
				}
			}
			cache.set(ctx, key, entry, ttl)
		}
		cache.inflight.Delete(key)
		close(f.done)

		for name, values := range rec.header {
			for _, value := range values {
				w.Header().Add(name, value)
			}
		}
		w.Header().Set("X-Contexta-Cache", "miss")
		w.WriteHeader(rec.status)
		_, _ = w.Write(rec.body)
	})
}

// responseRecorder buffers an upstream response so it can be cached, coalesced
// and replayed rather than streamed once.
type responseRecorder struct {
	header http.Header
	body   []byte
	status int
}

func (r *responseRecorder) Header() http.Header { return r.header }

func (r *responseRecorder) Write(p []byte) (int, error) {
	if r.status == 0 {
		r.status = http.StatusOK
	}
	r.body = append(r.body, p...)
	return len(p), nil
}

func (r *responseRecorder) WriteHeader(status int) {
	if r.status == 0 {
		r.status = status
	}
}
