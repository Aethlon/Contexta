package server

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// fakeRedis is an in-memory stand-in for Redis.
type fakeRedis struct {
	mu     sync.Mutex
	values map[string]string
	gets   int
	sets   int
}

func newFakeRedis() *fakeRedis { return &fakeRedis{values: map[string]string{}} }

func (f *fakeRedis) Get(_ context.Context, key string) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.gets++
	return f.values[key], nil
}

func (f *fakeRedis) Set(_ context.Context, key, value string, _ time.Duration) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.sets++
	f.values[key] = value
	return nil
}

func (f *fakeRedis) setCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.sets
}

// slowHandler counts upstream calls and blocks briefly so concurrent duplicates
// genuinely overlap.
func slowHandler(calls *int32, delay time.Duration) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		atomic.AddInt32(calls, 1)
		time.Sleep(delay)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"memories":[{"id":"m1"}]}`))
	})
}

func newRetrieveRequest(body string) *http.Request {
	r := httptest.NewRequest(http.MethodPost, "/v1/retrieve", strings.NewReader(body))
	r.Header.Set("X-Organization-Id", "org-1")
	r.Header.Set("X-User-Id", "user-1")
	r.Header.Set("X-Api-Key", "mk_live_test")
	return r
}

func TestCacheServesRepeatQueryWithoutUpstreamCall(t *testing.T) {
	redis := newFakeRedis()
	cache := &RetrievalCache{redis: redis, ttl: 30 * time.Second}
	var calls int32
	handler := CachedProxy(slowHandler(&calls, 0), cache)

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, newRetrieveRequest(`{"q":"hello"}`))
	if calls != 1 {
		t.Fatalf("expected 1 upstream call, got %d", calls)
	}
	if got := rec.Header().Get("X-Contexta-Cache"); got != "miss" {
		t.Fatalf("first call should be a miss, got %q", got)
	}

	rec2 := httptest.NewRecorder()
	handler.ServeHTTP(rec2, newRetrieveRequest(`{"q":"hello"}`))
	if calls != 1 {
		t.Fatalf("expected no additional upstream call on cache hit, got %d", calls)
	}
	if got := rec2.Header().Get("X-Contexta-Cache"); got != "hit" {
		t.Fatalf("second call should be a hit, got %q", got)
	}
	if rec2.Body.String() != rec.Body.String() {
		t.Fatalf("cached body differs:\n got %q\nwant %q", rec2.Body.String(), rec.Body.String())
	}
}

func TestCacheIsolatesTenants(t *testing.T) {
	redis := newFakeRedis()
	cache := &RetrievalCache{redis: redis, ttl: 30 * time.Second}
	var calls int32
	handler := CachedProxy(slowHandler(&calls, 0), cache)

	handler.ServeHTTP(httptest.NewRecorder(), newRetrieveRequest(`{"q":"same"}`))

	other := newRetrieveRequest(`{"q":"same"}`)
	other.Header.Set("X-Organization-Id", "org-2")
	handler.ServeHTTP(httptest.NewRecorder(), other)

	if calls != 2 {
		t.Fatalf("a different tenant must not read another tenant's cache entry; calls=%d", calls)
	}
}

func TestSingleFlightCoalescesConcurrentDuplicates(t *testing.T) {
	redis := newFakeRedis()
	cache := &RetrievalCache{redis: redis, ttl: 30 * time.Second}
	var calls int32
	handler := CachedProxy(slowHandler(&calls, 150*time.Millisecond), cache)

	const n = 8
	var wg sync.WaitGroup
	bodies := make([]string, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, newRetrieveRequest(`{"q":"burst"}`))
			bodies[idx] = rec.Body.String()
		}(i)
	}
	wg.Wait()

	if calls != 1 {
		t.Fatalf("single-flight should collapse %d duplicates into 1 upstream call, got %d", n, calls)
	}
	for i, body := range bodies {
		if body != bodies[0] {
			t.Fatalf("coalesced response %d differs from the first", i)
		}
	}
}

func TestWritesAreNeverCached(t *testing.T) {
	redis := newFakeRedis()
	cache := &RetrievalCache{redis: redis, ttl: 30 * time.Second}
	var calls int32
	handler := CachedProxy(slowHandler(&calls, 0), cache)

	r := httptest.NewRequest(http.MethodPost, "/v1/observations", strings.NewReader(`{}`))
	handler.ServeHTTP(httptest.NewRecorder(), r)
	r2 := httptest.NewRequest(http.MethodPost, "/v1/observations", strings.NewReader(`{}`))
	handler.ServeHTTP(httptest.NewRecorder(), r2)

	if calls != 2 {
		t.Fatalf("ingest must never be cached; calls=%d", calls)
	}
	if redis.setCount() != 0 {
		t.Fatalf("ingest wrote %d cache entries, expected 0", redis.setCount())
	}
}

func TestCacheDegradesWhenRedisUnavailable(t *testing.T) {
	cache := &RetrievalCache{redis: nil, ttl: time.Second}
	var calls int32
	handler := CachedProxy(slowHandler(&calls, 0), cache)

	handler.ServeHTTP(httptest.NewRecorder(), newRetrieveRequest(`{"q":"x"}`))
	handler.ServeHTTP(httptest.NewRecorder(), newRetrieveRequest(`{"q":"x"}`))

	if calls != 2 {
		t.Fatalf("without Redis every call must reach upstream, got %d", calls)
	}
}
