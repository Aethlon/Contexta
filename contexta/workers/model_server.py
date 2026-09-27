"""Persistent Local Model Server for Contexta Offline Inference."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("contexta.model_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None


class EmbeddingDataItem(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingDataItem]
    model: str
    profile: str | None = None
    dimensions: int | None = None
    backend: str | None = None
    usage: dict[str, int]


class ClassifyRequest(BaseModel):
    texts: list[str]
    labels: list[str] = Field(default_factory=lambda: ["preference", "fact", "goal", "event", "other"])


class ClassifyResult(BaseModel):
    text: str
    label: str
    score: float
    all_scores: dict[str, float]


class ClassifyResponse(BaseModel):
    predictions: list[ClassifyResult]
    model: str


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_n: int | None = None


class RerankResult(BaseModel):
    index: int
    document: str
    relevance_score: float


class RerankResponse(BaseModel):
    results: list[RerankResult]
    model: str


class ModelServerError(RuntimeError):
    """Base error for model-server admission and execution failures."""


class ModelServerUnavailableError(ModelServerError):
    """Raised when the model server cannot accept work."""


class ModelServerQueueFullError(ModelServerError):
    """Raised when an inference queue has reached its configured limit."""


class ModelServerRequestTooLargeError(ModelServerError):
    """Raised when an inference request exceeds its configured limit."""


_MODEL_ERRORS: tuple[type[BaseException], ...] = (Exception,)


QWEN_EMBEDDING_ID = "Qwen/Qwen3-Embedding-0.6B"
QWEN_EMBEDDING_DIR = "qwen3-embedding-0.6b"
QWEN_RERANKER_ID = "Qwen/Qwen3-Reranker-0.6B"
QWEN_RERANKER_DIR = "qwen3-reranker-0.6b"


def _env_int(default: int, *names: str) -> int:
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid integer environment variable %s=%r; using %d", name, raw, default)
    return default


def _env_float(default: float, *names: str) -> float:
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        try:
            return float(raw)
        except ValueError:
            logger.warning("Invalid float environment variable %s=%r; using %s", name, raw, default)
    return default


MAX_EMBEDDING_BATCH_SIZE = max(
    1,
    _env_int(
        32,
        "CONTEXTA_MODEL_MAX_EMBEDDING_BATCH_SIZE",
        "CONTEXTA_MODEL_MAX_BATCH_SIZE",
        "MODEL_SERVER_MAX_EMBEDDING_BATCH_SIZE",
    ),
)
MAX_EMBEDDING_QUEUE_SIZE = max(
    1,
    _env_int(
        256,
        "CONTEXTA_MODEL_MAX_EMBEDDING_QUEUE_SIZE",
        "CONTEXTA_MODEL_QUEUE_SIZE",
        "MODEL_SERVER_MAX_EMBEDDING_QUEUE_SIZE",
    ),
)
MAX_EMBEDDING_REQUEST_TEXTS = max(
    1,
    _env_int(
        256,
        "CONTEXTA_MODEL_MAX_EMBEDDING_REQUEST_TEXTS",
        "MODEL_SERVER_MAX_EMBEDDING_REQUEST_TEXTS",
    ),
)
MAX_EMBEDDING_TEXT_CHARS = max(
    1,
    _env_int(
        32_000,
        "CONTEXTA_MODEL_MAX_EMBEDDING_TEXT_CHARS",
        "MODEL_SERVER_MAX_EMBEDDING_TEXT_CHARS",
    ),
)
MAX_EMBEDDING_TOTAL_CHARS = max(
    1,
    _env_int(
        256_000,
        "CONTEXTA_MODEL_MAX_EMBEDDING_TOTAL_CHARS",
        "MODEL_SERVER_MAX_EMBEDDING_TOTAL_CHARS",
    ),
)
MAX_CLASSIFY_TEXTS = max(
    1,
    _env_int(
        128,
        "CONTEXTA_MODEL_MAX_CLASSIFY_TEXTS",
        "MODEL_SERVER_MAX_CLASSIFY_TEXTS",
    ),
)
MAX_CLASSIFY_TEXT_CHARS = max(
    1,
    _env_int(
        32_000,
        "CONTEXTA_MODEL_MAX_CLASSIFY_TEXT_CHARS",
        "MODEL_SERVER_MAX_CLASSIFY_TEXT_CHARS",
    ),
)
MAX_RERANK_DOCUMENTS = max(
    1,
    _env_int(
        128,
        "CONTEXTA_MODEL_MAX_RERANK_DOCUMENTS",
        "MODEL_SERVER_MAX_RERANK_DOCUMENTS",
    ),
)
MAX_RERANK_DOCUMENT_CHARS = max(
    1,
    _env_int(
        16_000,
        "CONTEXTA_MODEL_MAX_RERANK_DOCUMENT_CHARS",
        "MODEL_SERVER_MAX_RERANK_DOCUMENT_CHARS",
    ),
)
MAX_RERANK_QUERY_CHARS = max(
    1,
    _env_int(
        4_000,
        "CONTEXTA_MODEL_MAX_RERANK_QUERY_CHARS",
        "MODEL_SERVER_MAX_RERANK_QUERY_CHARS",
    ),
)
MAX_RERANK_TOTAL_CHARS = max(
    1,
    _env_int(
        512_000,
        "CONTEXTA_MODEL_MAX_RERANK_TOTAL_CHARS",
        "MODEL_SERVER_MAX_RERANK_TOTAL_CHARS",
    ),
)
MAX_RERANK_QUEUE_SIZE = max(
    1,
    _env_int(
        32,
        "CONTEXTA_MODEL_MAX_RERANK_QUEUE_SIZE",
        "MODEL_SERVER_MAX_RERANK_QUEUE_SIZE",
    ),
)
MAX_RERANK_CONCURRENCY = max(
    1,
    _env_int(
        2,
        "CONTEXTA_MODEL_MAX_RERANK_CONCURRENCY",
        "MODEL_SERVER_MAX_RERANK_CONCURRENCY",
    ),
)
MAX_EMBEDDING_CONCURRENCY = max(
    1,
    _env_int(
        1,
        "CONTEXTA_MODEL_MAX_EMBEDDING_CONCURRENCY",
        "MODEL_SERVER_MAX_EMBEDDING_CONCURRENCY",
    ),
)
MAX_REQUEST_BYTES = max(
    1_024,
    _env_int(
        4_000_000,
        "CONTEXTA_MODEL_MAX_REQUEST_BYTES",
        "MODEL_SERVER_MAX_REQUEST_BYTES",
    ),
)
BATCH_WINDOW_SECONDS = max(
    0.0,
    _env_float(
        0.005,
        "CONTEXTA_MODEL_BATCH_WINDOW_SECONDS",
        "MODEL_SERVER_BATCH_WINDOW_SECONDS",
    ),
)


def _resolve_local_model_dir(dirname: str) -> str | None:
    base = os.environ.get("MODEL_CACHE_DIR", os.environ.get("CONTEXTA_MODEL_CACHE_DIR", "models"))
    path = os.path.join(base, dirname)
    if not os.path.isdir(path):
        return None
    try:
        names = os.listdir(path)
    except OSError:
        return None
    if any(name.endswith(".safetensors") for name in names) or any(name.endswith(".bin") for name in names):
        return path
    if os.path.exists(os.path.join(path, "config.json")):
        return path
    return None


def _is_qwen_embedding_model(model_name: str) -> bool:
    normalized = model_name.strip().casefold()
    return normalized in {QWEN_EMBEDDING_ID.casefold(), QWEN_EMBEDDING_DIR.casefold()} or normalized.startswith(
        "qwen3-embedding-"
    )


def _model_device(model: Any) -> str | None:
    device = getattr(model, "device", None)
    if device is None:
        return None
    text = str(device)
    return text if text else None


def _align_reranker_pad_token(cross_encoder: Any) -> None:
    """Give Qwen3ForSequenceClassification the pad token its tokenizer already has.

    The model refuses any batch larger than one while `config.pad_token_id` is
    None, even though the tokenizer defines a pad token: a single-document rerank
    scored fine, so a batch of candidates raised ValueError, surfaced as 503, and
    the retrieval path fell back to the unreranked order. Reranking only ever
    sees one document when there is one candidate, which is why this stayed
    hidden. Copying the tokenizer's id across is the documented remedy.
    """
    tokenizer = getattr(cross_encoder, "tokenizer", None)
    pad_token_id = getattr(tokenizer, "pad_token_id", None)
    if pad_token_id is None:
        if getattr(tokenizer, "pad_token", None) is None:
            logger.warning("Reranker tokenizer has no pad token; multi-candidate rerank will fail.")
        return
    config = getattr(getattr(cross_encoder, "model", None), "config", None)
    if config is not None and getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = pad_token_id


class DynamicMicroBatcher:
    """Collect embedding requests and run bounded batches in a dedicated executor."""

    def __init__(
        self,
        batch_window_seconds: float = BATCH_WINDOW_SECONDS,
        max_batch_size: int = MAX_EMBEDDING_BATCH_SIZE,
        max_queue_size: int = MAX_EMBEDDING_QUEUE_SIZE,
        max_concurrency: int = MAX_EMBEDDING_CONCURRENCY,
    ) -> None:
        self.batch_window = max(0.0, float(batch_window_seconds))
        self.max_batch_size = max(1, int(max_batch_size))
        self.max_queue_size = max(1, int(max_queue_size))
        self.max_concurrency = max(1, int(max_concurrency))
        self.queue: asyncio.Queue[tuple[str, asyncio.Future[list[float]]]] = asyncio.Queue(
            maxsize=self.max_queue_size,
        )
        self._worker_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_futures: set[asyncio.Future[list[float]]] = set()
        self._running = False
        self._accepting = False
        self._state = "created"
        self._last_error: str | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._active_batches = 0
        self._batches_processed = 0
        self._texts_processed = 0
        self.embedding_dimensions = max(1, int(os.environ.get("CONTEXTA_EMBEDDING_DIMENSIONS", "1024")))
        self._st_model = None
        self._backend = "unavailable"
        configured_model = os.environ.get("CONTEXTA_EMBEDDING_MODEL", "").strip() or QWEN_EMBEDDING_ID
        self._configured_model = configured_model
        self._backend_model = configured_model
        self._model_path: str | None = None
        self._load_error: str | None = None
        if not _is_qwen_embedding_model(configured_model):
            self._load_error = (
                f"unsupported embedding model {configured_model!r}; the offline engine only serves "
                f"{QWEN_EMBEDDING_ID}"
            )
            logger.error(self._load_error)
            return
        try:
            qwen_path = _resolve_local_model_dir(QWEN_EMBEDDING_DIR) or QWEN_EMBEDDING_ID
            from sentence_transformers import SentenceTransformer

            self._st_model = SentenceTransformer(qwen_path, trust_remote_code=True)
            self._backend = "qwen3"
            self._backend_model = QWEN_EMBEDDING_ID
            self._model_path = qwen_path
            self._state = "loaded"
            logger.info("Qwen3 embedding backend ready (%s).", qwen_path)
        except _MODEL_ERRORS as exc:
            self._load_error = f"qwen3: {exc}"
            logger.error("Qwen3 embedding model failed to load (%s); refusing to serve.", exc)

    @property
    def running(self) -> bool:
        return self._state in {"running", "idle"} and (self._loop is None or self._loop.is_running())

    @property
    def accepting(self) -> bool:
        return self._state in {"running", "idle"} and self._loop is not None and self._loop.is_running()

    @property
    def state(self) -> str:
        return self._state

    @property
    def queue_size(self) -> int:
        return self.queue.qsize()

    @property
    def pending_count(self) -> int:
        return len(self._pending_futures)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def backend_model(self) -> str:
        return self._backend_model

    @property
    def model_path(self) -> str | None:
        return self._model_path

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def _ensure_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is loop:
            return
        if self._loop is not None:
            failure = ModelServerUnavailableError("Embedding batcher event loop changed")
            worker = self._worker_task
            self._worker_task = None
            if worker is not None and not worker.get_loop().is_closed():
                worker.cancel()
            self._running = False
            self._accepting = False
            self._state = "created"
            self._fail_pending(failure)
            self._drain_queue(failure)
            executor = self._executor
            self._executor = None
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            self.queue = asyncio.Queue(maxsize=self.max_queue_size)
            self._active_batches = 0
        self._loop = loop

    def start(self) -> None:
        self._ensure_loop()
        if self._running:
            return
        self._running = True
        self._accepting = True
        self._state = "running"
        self._last_error = None
        self._worker_task = asyncio.create_task(self._process_loop())
        logger.info(
            "Dynamic micro-batcher started (window=%sms, max_batch=%d, queue=%d)",
            int(self.batch_window * 1000),
            self.max_batch_size,
            self.max_queue_size,
        )

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_concurrency,
                thread_name_prefix="contexta-embedding",
            )
        return self._executor

    def _set_future_exception(self, future: asyncio.Future[list[float]], error: BaseException) -> None:
        if future.done():
            return
        if isinstance(error, asyncio.CancelledError):
            error = ModelServerUnavailableError("Embedding batcher stopped")
        future.set_exception(error)
        self._pending_futures.discard(future)

    def _fail_pending(self, error: BaseException | None = None) -> None:
        failure = error or ModelServerUnavailableError("Embedding batcher stopped")
        for future in tuple(self._pending_futures):
            self._set_future_exception(future, failure)

    def _drain_queue(self, error: BaseException) -> None:
        while True:
            try:
                _, future = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._set_future_exception(future, error)

    async def stop(self) -> None:
        current_loop = asyncio.get_running_loop()
        same_loop = self._loop is current_loop
        self._running = False
        self._accepting = False
        self._state = "stopped"
        worker = self._worker_task
        self._worker_task = None
        if worker is not None and worker is not asyncio.current_task():
            worker_loop = worker.get_loop()
            if same_loop:
                worker.cancel()
            elif not worker_loop.is_closed():
                worker_loop.call_soon_threadsafe(worker.cancel)
            if same_loop:
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
                except _MODEL_ERRORS as exc:
                    self._last_error = str(exc)
        shutdown_error = ModelServerUnavailableError("Embedding batcher stopped")
        self._fail_pending(shutdown_error)
        self._drain_queue(shutdown_error)
        executor = self._executor
        self._executor = None
        if executor is not None:
            if same_loop:
                await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
            else:
                executor.shutdown(wait=False, cancel_futures=True)
        self._active_batches = 0
        self._loop = None
        self.queue = asyncio.Queue(maxsize=self.max_queue_size)

    async def embed_single(self, text: str) -> list[float]:
        self._ensure_loop()
        if not self._running:
            self.start()
        if not self._accepting:
            raise ModelServerUnavailableError("Embedding batcher is not accepting work")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[float]] = loop.create_future()
        self._pending_futures.add(future)
        try:
            self.queue.put_nowait((text, future))
        except asyncio.QueueFull as exc:
            self._pending_futures.discard(future)
            raise ModelServerQueueFullError(
                f"Embedding queue is full ({self.max_queue_size} requests)",
            ) from exc
        try:
            return await future
        finally:
            self._pending_futures.discard(future)

    async def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for start in range(0, len(texts), self.max_batch_size):
            chunk = list(texts[start : start + self.max_batch_size])
            tasks = [asyncio.create_task(self.embed_single(text)) for text in chunk]
            try:
                values = await asyncio.gather(*tasks, return_exceptions=True)
            except BaseException:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            failure: BaseException | None = None
            for value in values:
                if isinstance(value, BaseException):
                    failure = failure or value
            if failure is not None:
                raise failure
            results.extend(values)
        return results

    async def compute(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_loop()
        if not self._running:
            self.start()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(self._get_executor(), self._compute_batch, list(texts))
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _process_loop(self) -> None:
        current_items: list[tuple[str, asyncio.Future[list[float]]]] = []
        try:
            while self._running:
                try:
                    current_items = [await self.queue.get()]
                    batch_started = time.monotonic()
                    while len(current_items) < self.max_batch_size and self._running:
                        remaining = self.batch_window - (time.monotonic() - batch_started)
                        if remaining <= 0:
                            break
                        try:
                            current_items.append(await asyncio.wait_for(self.queue.get(), timeout=remaining))
                        except TimeoutError:
                            break
                    pending_items = [item for item in current_items if not item[1].done()]
                    if not pending_items:
                        current_items = []
                        continue
                    texts = [item[0] for item in pending_items]
                    futures = [item[1] for item in pending_items]
                    self._active_batches += 1
                    try:
                        loop = asyncio.get_running_loop()
                        embeddings = await loop.run_in_executor(
                            self._get_executor(),
                            self._compute_batch,
                            texts,
                        )
                        if inspect.isawaitable(embeddings):
                            embeddings = await embeddings
                    finally:
                        self._active_batches -= 1
                    if len(embeddings) != len(futures):
                        raise ModelServerUnavailableError("Embedding backend returned an incomplete batch")
                    for future, embedding in zip(futures, embeddings):
                        if not future.done():
                            future.set_result(embedding)
                    self._batches_processed += 1
                    self._texts_processed += len(futures)
                    current_items = []
                    if self.queue.empty():
                        self._running = False
                        self._accepting = False
                        self._state = "idle"
                        self._worker_task = None
                        return
                except asyncio.CancelledError:
                    raise
                except _MODEL_ERRORS as exc:
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._accepting = False
                    self._running = False
                    self._state = "failed"
                    failure = exc if isinstance(exc, ModelServerError) else ModelServerUnavailableError(
                        f"Embedding backend failed: {exc}",
                    )
                    logger.exception("Embedding micro-batch failed")
                    self._fail_pending(failure)
                    self._drain_queue(failure)
                    break
        finally:
            if not self._running:
                self._fail_pending(ModelServerUnavailableError("Embedding batcher stopped"))
                self._drain_queue(ModelServerUnavailableError("Embedding batcher stopped"))

    def _compute_batch(self, texts: list[str]) -> list[list[float]]:
        dims = self.embedding_dimensions

        def validate(values: list[float], backend: str) -> list[float]:
            if len(values) != dims:
                raise ModelServerError(
                    f"{backend} returned {len(values)} dimensions; expected {dims}. "
                    "Configure a native embedding model for the active profile; "
                    "padding, truncation, and hash fallback are disabled."
                )
            return values

        if self._st_model is None:
            raise ModelServerError(
                "Qwen3 embedding model is not loaded. "
                f"Install sentence-transformers and provide {QWEN_EMBEDDING_ID}; "
                "the offline engine never substitutes another model or profile."
            )
        vectors = self._st_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vector_list = list(vectors)
        if len(vector_list) != len(texts):
            raise ModelServerError("Qwen3 embedding backend returned an incomplete batch")
        results = [validate([float(value) for value in list(vector)], "qwen3") for vector in vector_list]
        self._backend = "qwen3"
        self._backend_model = QWEN_EMBEDDING_ID
        return results


class LocalModelEngine:
    """Manage embedding and reranking workloads with separate admission controls."""

    def __init__(
        self,
        *,
        batch_window_seconds: float = BATCH_WINDOW_SECONDS,
        max_batch_size: int = MAX_EMBEDDING_BATCH_SIZE,
        max_embedding_queue_size: int = MAX_EMBEDDING_QUEUE_SIZE,
        max_embedding_request_texts: int = MAX_EMBEDDING_REQUEST_TEXTS,
        max_rerank_queue_size: int = MAX_RERANK_QUEUE_SIZE,
        max_rerank_documents: int = MAX_RERANK_DOCUMENTS,
        max_rerank_concurrency: int = MAX_RERANK_CONCURRENCY,
        max_embedding_concurrency: int = MAX_EMBEDDING_CONCURRENCY,
    ) -> None:
        self.embedding_profile_name = os.environ.get(
            "CONTEXTA_EMBEDDING_PROFILE",
            "offline-qwen3-1024",
        ).strip()
        self.embedding_model_name = os.environ.get(
            "CONTEXTA_EMBEDDING_MODEL",
            QWEN_EMBEDDING_ID,
        ).strip() or QWEN_EMBEDDING_ID
        self.reranker_model_name = QWEN_RERANKER_ID
        self.cache_dir = os.environ.get("MODEL_CACHE_DIR", os.environ.get("CONTEXTA_MODEL_CACHE_DIR", "models"))
        self.max_batch_size = max(1, int(max_batch_size))
        self.max_embedding_queue_size = max(1, int(max_embedding_queue_size))
        self.max_embedding_request_texts = max(1, int(max_embedding_request_texts))
        self.max_rerank_queue_size = max(1, int(max_rerank_queue_size))
        self.max_rerank_documents = max(1, int(max_rerank_documents))
        self.max_rerank_concurrency = max(1, int(max_rerank_concurrency))
        self.max_embedding_concurrency = max(1, int(max_embedding_concurrency))
        self.batcher = DynamicMicroBatcher(
            batch_window_seconds=batch_window_seconds,
            max_batch_size=self.max_batch_size,
            max_queue_size=self.max_embedding_queue_size,
            max_concurrency=self.max_embedding_concurrency,
        )
        self.loaded_at: float | None = None
        self.download_status: dict[str, bool] = {}
        self.embedding_latency_samples: list[float] = []
        self.reranker_latency_samples: list[float] = []
        self._cross_encoder = None
        self._ce_backend = "none"
        self._ce_model = "semantic-fallback"
        self._reranker_load_error: str | None = None
        self.device = "cpu"
        self.ram_usage_mb: float | None = None
        self._state = "created"
        self._accepting = True
        self._closed = False
        self._last_error: str | None = None
        self._rerank_pending = 0
        self._rerank_active = 0
        self._rerank_semaphore: asyncio.Semaphore | None = None
        self._rerank_semaphore_loop: asyncio.AbstractEventLoop | None = None
        self._rerank_executor: ThreadPoolExecutor | None = None
        try:
            ce_path = _resolve_local_model_dir(QWEN_RERANKER_DIR) or QWEN_RERANKER_ID
            from sentence_transformers import CrossEncoder

            self._cross_encoder = CrossEncoder(ce_path, trust_remote_code=True)
            _align_reranker_pad_token(self._cross_encoder)
            self._ce_backend = "qwen3"
            self._ce_model = QWEN_RERANKER_ID
            logger.info("Qwen3 reranker backend ready (%s).", ce_path)
        except _MODEL_ERRORS as exc:
            self._reranker_load_error = f"qwen3: {exc}"
            logger.error("Qwen3 reranker failed to load (%s); refusing to substitute another model.", exc)
        self.device = _model_device(self.batcher._st_model) or _model_device(self._cross_encoder) or "cpu"

    @property
    def state(self) -> str:
        return self._state

    @property
    def ready(self) -> bool:
        return self._state == "ready" and self.batcher.running and not self._closed

    @property
    def accepting_requests(self) -> bool:
        return self.batcher.accepting and not self._closed and (self._accepting or self.batcher.state == "idle")

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @staticmethod
    def _record_latency(samples: list[float], value: float) -> None:
        samples.append(value)
        if len(samples) > 100:
            del samples[:-100]

    async def warm_up(self) -> None:
        self._closed = False
        self._accepting = True
        self._state = "warming"
        self._last_error = None
        logger.info("Checking persistent offline model cache in %s...", self.cache_dir)
        try:
            from scripts.download_offline_models import ensure_models_downloaded

            self.download_status = await asyncio.to_thread(ensure_models_downloaded, self.cache_dir)
            logger.info("Persistent model cache verification: %s", self.download_status)
        except _MODEL_ERRORS as exc:
            self._last_error = f"model cache: {exc}"
            logger.warning("Could not auto-download offline models (%s); using loaded backends.", exc)
        logger.info("Initializing in-memory weights for %s and %s...", self.embedding_model_name, self.reranker_model_name)
        started = time.monotonic()
        try:
            self.batcher.start()
            await self.batcher.embed_single("Contexta offline warm-up query")
            self.loaded_at = time.time()
            self._state = "ready"
            self._accepting = True
            logger.info("Models loaded and warmed in RAM in %.2fs. Persistent inference ready.", time.monotonic() - started)
        except asyncio.CancelledError:
            self._state = "stopping"
            self._accepting = False
            raise
        except _MODEL_ERRORS as exc:
            self._state = "failed"
            self._accepting = False
            self._last_error = f"warmup: {exc}"
            await self.batcher.stop()
            raise

    async def shutdown(self) -> None:
        if self._state == "stopped" and self._closed:
            return
        self._state = "stopping"
        self._accepting = False
        self._closed = True
        await self.batcher.stop()
        executor = self._rerank_executor
        self._rerank_executor = None
        if executor is not None:
            await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
        self._rerank_semaphore = None
        self._rerank_semaphore_loop = None
        self._state = "stopped"

    async def _ensure_available(self) -> None:
        if self._closed or self._state in {"warming", "stopping", "stopped"}:
            raise ModelServerUnavailableError("Model server is not ready")
        if not self.batcher.running:
            self.batcher.start()
        if self.loaded_at is None:
            self.loaded_at = time.time()
        if self._state in {"created", "starting", "failed"}:
            self._state = "ready"
        self._accepting = True

    async def get_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > self.max_embedding_request_texts:
            raise ModelServerRequestTooLargeError(
                f"Embedding request contains too many items ({len(texts)} > {self.max_embedding_request_texts})",
            )
        await self._ensure_available()
        started = time.monotonic()
        results = await self.batcher.embed_many(texts)
        if len(results) != len(texts):
            raise ModelServerUnavailableError("Embedding backend returned an incomplete response")
        self._record_latency(self.embedding_latency_samples, (time.monotonic() - started) * 1000)
        return results

    async def classify(self, texts: Sequence[str], labels: Sequence[str]) -> list[ClassifyResult]:
        if len(texts) > MAX_CLASSIFY_TEXTS or len(labels) > 32:
            raise ModelServerRequestTooLargeError("Classification request contains too many items")
        if not labels:
            raise ModelServerRequestTooLargeError("Classification labels cannot be empty")
        started = time.monotonic()
        await self._ensure_available()
        neural = await self._classify_neural(texts, labels)
        if neural is not None:
            self._record_latency(self.reranker_latency_samples, (time.monotonic() - started) * 1000)
            return neural
        results: list[ClassifyResult] = []
        for text in texts:
            scores = self._keyword_scores(text, labels)
            total = sum(scores.values()) or 1.0
            normalized = {key: round(value / total, 4) for key, value in scores.items()}
            best_label = max(normalized.items(), key=lambda item: item[1])
            results.append(
                ClassifyResult(
                    text=text,
                    label=best_label[0],
                    score=best_label[1],
                    all_scores=normalized,
                )
            )
        self._record_latency(self.reranker_latency_samples, (time.monotonic() - started) * 1000)
        return results

    _LABEL_PROTOTYPES = {
        "preference": "preference likes prefers loves favorite choice enjoys wants",
        "fact": "fact is born works uses built located lives",
        "goal": "goal want plan aim target launch will achieve",
        "event": "event yesterday tomorrow scheduled meeting happened occurred",
    }

    async def _classify_neural(self, texts: Sequence[str], labels: Sequence[str]) -> list[ClassifyResult] | None:
        if self.batcher._st_model is None:
            return None
        try:
            prototypes = [self._LABEL_PROTOTYPES.get(label, label) for label in labels]
            vectors = await self.batcher.embed_many([*texts, *prototypes])
            text_vectors = vectors[: len(texts)]
            prototype_vectors = vectors[len(texts) :]
            import math

            output: list[ClassifyResult] = []
            for text, text_vector in zip(texts, text_vectors):
                similarities: dict[str, float] = {}
                for label, prototype_vector in zip(labels, prototype_vectors):
                    dot = sum(a * b for a, b in zip(text_vector, prototype_vector))
                    norm_text = math.sqrt(sum(a * a for a in text_vector)) or 1.0
                    norm_prototype = math.sqrt(sum(a * a for a in prototype_vector)) or 1.0
                    similarities[label] = max(0.0, dot / (norm_text * norm_prototype))
                keyword_scores = self._keyword_scores(text, labels)
                keyword_total = sum(keyword_scores.values()) or 1.0
                blended = {
                    label: 0.7 * similarities.get(label, 0.0) + 0.3 * (keyword_scores.get(label, 0.2) / keyword_total)
                    for label in labels
                }
                total = sum(blended.values()) or 1.0
                normalized = {key: round(value / total, 4) for key, value in blended.items()}
                best_label = max(normalized.items(), key=lambda item: item[1])
                output.append(
                    ClassifyResult(
                        text=text,
                        label=best_label[0],
                        score=best_label[1],
                        all_scores=normalized,
                    )
                )
            return output
        except ModelServerError:
            raise
        except asyncio.CancelledError:
            raise
        except _MODEL_ERRORS as exc:
            logger.warning("Neural classify failed (%s); using keyword fallback.", exc)
            return None

    @staticmethod
    def _keyword_scores(text: str, labels: Sequence[str]) -> dict[str, float]:
        lowered = text.lower()
        scores: dict[str, float] = {}
        for label in labels:
            base_score = 0.2
            if label == "preference" and any(key in lowered for key in ["prefer", "like", "love", "favorite", "choice"]):
                base_score = 0.88
            elif label == "fact" and any(key in lowered for key in ["is", "born", "works", "uses", "built", "located"]):
                base_score = 0.82
            elif label == "goal" and any(key in lowered for key in ["want", "plan", "goal", "aim", "target"]):
                base_score = 0.85
            elif label == "event" and any(
                key in lowered for key in ["yesterday", "tomorrow", "scheduled", "meeting", "happened"]
            ):
                base_score = 0.80
            scores[label] = base_score
        return scores

    def _get_rerank_executor(self) -> ThreadPoolExecutor:
        if self._rerank_executor is None:
            self._rerank_executor = ThreadPoolExecutor(
                max_workers=self.max_rerank_concurrency,
                thread_name_prefix="contexta-rerank",
            )
        return self._rerank_executor

    def _get_rerank_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._rerank_semaphore is None or self._rerank_semaphore_loop is not loop:
            self._rerank_semaphore = asyncio.Semaphore(self.max_rerank_concurrency)
            self._rerank_semaphore_loop = loop
        return self._rerank_semaphore

    def _reserve_rerank(self) -> asyncio.Semaphore:
        if not self._accepting or self._closed or self._state in {"stopping", "stopped"}:
            raise ModelServerUnavailableError("Reranker is not accepting work")
        if self._rerank_pending >= self.max_rerank_queue_size:
            raise ModelServerQueueFullError(
                f"Rerank queue is full ({self.max_rerank_queue_size} requests)",
            )
        self._rerank_pending += 1
        return self._get_rerank_semaphore()

    def _release_rerank(self, semaphore: asyncio.Semaphore, acquired: bool) -> None:
        if acquired:
            semaphore.release()
        self._rerank_active = max(0, self._rerank_active - (1 if acquired else 0))
        self._rerank_pending = max(0, self._rerank_pending - 1)

    async def rerank(self, query: str, documents: Sequence[str], top_n: int | None = None) -> list[RerankResult]:
        if len(documents) > self.max_rerank_documents:
            raise ModelServerRequestTooLargeError(
                f"Rerank request contains too many documents ({len(documents)} > {self.max_rerank_documents})",
            )
        if len(query) > MAX_RERANK_QUERY_CHARS:
            raise ModelServerRequestTooLargeError("Rerank query is too large")
        if not documents:
            return []
        await self._ensure_available()
        semaphore = self._reserve_rerank()
        acquired = False
        started = time.monotonic()
        try:
            await semaphore.acquire()
            acquired = True
            self._rerank_active += 1
            if not self._accepting or self._closed:
                raise ModelServerUnavailableError("Reranker stopped while request was queued")
            if self._cross_encoder is None:
                raise ModelServerUnavailableError(
                    f"Qwen3 reranker {QWEN_RERANKER_ID} is not loaded; "
                    "refusing to score candidates with a non-neural fallback."
                )
            try:
                loop = asyncio.get_running_loop()
                executor = self._get_rerank_executor()
                pairs = [[query, document] for document in documents]
                scores = await loop.run_in_executor(
                    executor,
                    self._cross_encoder.predict,
                    pairs,
                )
                score_values = list(scores)
                if len(score_values) != len(documents):
                    raise ModelServerError("Qwen3 reranker returned an incomplete batch")
                scored = [
                    RerankResult(
                        index=index,
                        document=document,
                        relevance_score=float(score),
                    )
                    for index, (document, score) in enumerate(zip(documents, score_values))
                ]
                scored.sort(key=lambda result: result.relevance_score, reverse=True)
                if top_n is not None and top_n > 0:
                    scored = scored[:top_n]
                self._record_latency(self.reranker_latency_samples, (time.monotonic() - started) * 1000)
                return scored
            except ModelServerError:
                raise
            except asyncio.CancelledError:
                raise
            except _MODEL_ERRORS as exc:
                if self._closed or not self._accepting:
                    raise ModelServerUnavailableError("Reranker stopped during inference") from exc
                raise ModelServerError(f"Qwen3 reranker inference failed: {exc}") from exc
        finally:
            self._release_rerank(semaphore, acquired)

    @staticmethod
    def _average_latency(samples: list[float]) -> float | None:
        if not samples:
            return None
        return round(sum(samples) / len(samples), 2)

    def status_payload(self) -> dict[str, Any]:
        embedding_backend = self.batcher.backend
        embedding_loaded = self.batcher._st_model is not None
        if self._state in {"stopping", "stopped"}:
            embedding_status = "stopped"
        elif self.batcher.state == "failed":
            embedding_status = "failed"
        elif not embedding_loaded:
            embedding_status = "unavailable"
        elif not self.batcher.running:
            embedding_status = "loaded"
        elif self._state in {"created", "starting", "warming"}:
            embedding_status = self._state
        else:
            embedding_status = "ready"
        reranker_loaded = self._cross_encoder is not None
        if self._state in {"stopping", "stopped"}:
            reranker_status = "stopped"
        elif not reranker_loaded:
            reranker_status = "unavailable"
        elif self._state in {"created", "starting", "warming"}:
            reranker_status = "loaded"
        else:
            reranker_status = "ready"
        fallback_active = embedding_backend != "qwen3" or not embedding_loaded or not reranker_loaded
        effective_state = self._state
        if self._state == "ready" and self.batcher.state in {"failed", "stopped"}:
            effective_state = self.batcher.state
        if self.ready:
            top_status = "degraded" if fallback_active else "healthy"
        else:
            top_status = effective_state
        return {
            "status": top_status,
            "state": effective_state,
            "ready": self.ready,
            "accepting": self.accepting_requests,
            "batcher_state": self.batcher.state,
            "service": "contexta-model-server",
            "device": self.device,
            "loaded_at": self.loaded_at,
            "ram_usage_mb": self.ram_usage_mb,
            "download_status": self.download_status,
            "last_error": self.last_error or self.batcher.last_error,
            "load_errors": {
                "embedding": self.batcher.load_error,
                "reranker": self._reranker_load_error,
            },
            "backend": {
                "embedding": embedding_backend,
                "reranker": self._ce_backend,
            },
            "embedding_model": {
                "name": self.embedding_model_name,
                "profile": self.embedding_profile_name,
                "active_model": self.batcher.backend_model,
                "status": embedding_status,
                "backend": embedding_backend,
                "loaded": embedding_loaded,
                "fallback": embedding_backend != "qwen3",
                "dimensions": self.batcher.embedding_dimensions,
                "avg_latency_ms": self._average_latency(self.embedding_latency_samples),
                "queue_depth": self.batcher.queue_size,
                "pending": self.batcher.pending_count,
                "max_queue_size": self.batcher.max_queue_size,
                "max_batch_size": self.batcher.max_batch_size,
            },
            "reranker_model": {
                "name": self.reranker_model_name,
                "active_model": self._ce_model,
                "status": reranker_status,
                "backend": self._ce_backend,
                "loaded": reranker_loaded,
                "fallback": not reranker_loaded,
                "avg_latency_ms": self._average_latency(self.reranker_latency_samples),
                "pending": self._rerank_pending,
                "active": self._rerank_active,
                "max_queue_size": self.max_rerank_queue_size,
                "max_concurrency": self.max_rerank_concurrency,
            },
            "queues": {
                "embedding": {
                    "depth": self.batcher.queue_size,
                    "pending": self.batcher.pending_count,
                    "limit": self.batcher.max_queue_size,
                    "active_batches": self.batcher._active_batches,
                },
                "rerank": {
                    "pending": self._rerank_pending,
                    "active": self._rerank_active,
                    "limit": self.max_rerank_queue_size,
                },
            },
            "limits": {
                "embedding_batch_size": self.max_batch_size,
                "embedding_queue_size": self.max_embedding_queue_size,
                "embedding_request_texts": self.max_embedding_request_texts,
                "rerank_documents": self.max_rerank_documents,
                "rerank_queue_size": self.max_rerank_queue_size,
                "rerank_concurrency": self.max_rerank_concurrency,
                "request_bytes": MAX_REQUEST_BYTES,
            },
        }


engine = LocalModelEngine()


def _request_size(request: BaseModel) -> int:
    return len(request.model_dump_json().encode("utf-8"))


def _validate_texts(
    texts: Sequence[str],
    *,
    max_count: int,
    max_text_chars: int,
    max_total_chars: int,
    label: str,
) -> None:
    if len(texts) > max_count:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label} contains too many items ({len(texts)} > {max_count}).",
        )
    total_chars = 0
    for text in texts:
        if len(text) > max_text_chars:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{label} item exceeds {max_text_chars} characters.",
            )
        total_chars += len(text)
    if total_chars > max_total_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label} exceeds {max_total_chars} total characters.",
        )


def _validate_payload_size(request: BaseModel, max_bytes: int = MAX_REQUEST_BYTES) -> None:
    if _request_size(request) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Request exceeds {max_bytes} bytes.",
        )


def _raise_inference_http_error(exc: ModelServerError) -> HTTPException:
    if isinstance(exc, ModelServerRequestTooLargeError):
        return HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    if isinstance(exc, ModelServerQueueFullError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "1"},
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
        headers={"Retry-After": "1"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.warm_up()
    try:
        yield
    finally:
        await engine.shutdown()


app = FastAPI(
    title="Contexta Persistent Local Model Server",
    version="1.0.0",
    description="Bounded local inference for Qwen3 embeddings and reranking",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    status_payload = engine.status_payload()
    return {
        "status": "healthy",
        "service": "contexta-model-server",
        "state": status_payload["state"],
        "ready": status_payload["ready"],
        "backend": status_payload["backend"],
    }


@app.get("/ready")
@app.get("/readyz")
@app.get("/readiness")
async def readiness() -> Any:
    payload = engine.status_payload()
    if not payload["ready"]:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return payload


@app.get("/models/status")
async def models_status() -> dict[str, Any]:
    return engine.status_payload()


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(req: EmbeddingRequest) -> EmbeddingResponse:
    requested_model = str(req.model).strip() if req.model else ""
    if requested_model and requested_model not in {
        engine.embedding_model_name,
        engine.batcher.backend_model,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested embedding model {requested_model!r} does not match the active model "
                f"{engine.batcher.backend_model!r}."
            ),
        )
    texts = [req.input] if isinstance(req.input, str) else req.input
    if not texts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input text cannot be empty.")
    _validate_texts(
        texts,
        max_count=engine.max_embedding_request_texts,
        max_text_chars=MAX_EMBEDDING_TEXT_CHARS,
        max_total_chars=MAX_EMBEDDING_TOTAL_CHARS,
        label="Embedding input",
    )
    _validate_payload_size(req)
    try:
        vectors = await engine.get_embeddings(texts)
    except ModelServerError as exc:
        raise _raise_inference_http_error(exc) from exc
    data_items = [EmbeddingDataItem(index=index, embedding=vector) for index, vector in enumerate(vectors)]
    total_tokens = sum(len(text.split()) for text in texts)
    return EmbeddingResponse(
        object="list",
        data=data_items,
        model=engine.batcher.backend_model,
        profile=engine.embedding_profile_name,
        dimensions=engine.batcher.embedding_dimensions,
        backend=engine.batcher.backend,
        usage={"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    )


@app.post("/v1/classify", response_model=ClassifyResponse)
async def classify_memories(req: ClassifyRequest) -> ClassifyResponse:
    if not req.texts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Texts list cannot be empty.")
    if not req.labels:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Labels list cannot be empty.")
    _validate_texts(
        req.texts,
        max_count=MAX_CLASSIFY_TEXTS,
        max_text_chars=MAX_CLASSIFY_TEXT_CHARS,
        max_total_chars=MAX_EMBEDDING_TOTAL_CHARS,
        label="Classification input",
    )
    _validate_texts(
        req.labels,
        max_count=32,
        max_text_chars=128,
        max_total_chars=1_024,
        label="Classification labels",
    )
    _validate_payload_size(req)
    try:
        predictions = await engine.classify(req.texts, req.labels)
    except ModelServerError as exc:
        raise _raise_inference_http_error(exc) from exc
    return ClassifyResponse(predictions=predictions, model=engine.reranker_model_name)


@app.post("/v1/rerank", response_model=RerankResponse)
async def rerank_candidates(req: RerankRequest) -> RerankResponse:
    if len(req.query) > MAX_RERANK_QUERY_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Rerank query exceeds {MAX_RERANK_QUERY_CHARS} characters.",
        )
    if req.top_n is not None and req.top_n < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="top_n cannot be negative.")
    _validate_texts(
        req.documents,
        max_count=engine.max_rerank_documents,
        max_text_chars=MAX_RERANK_DOCUMENT_CHARS,
        max_total_chars=MAX_RERANK_TOTAL_CHARS,
        label="Rerank documents",
    )
    _validate_payload_size(req)
    if not req.documents:
        return RerankResponse(results=[], model=engine.reranker_model_name)
    try:
        results = await engine.rerank(req.query, req.documents, req.top_n)
    except ModelServerError as exc:
        raise _raise_inference_http_error(exc) from exc
    return RerankResponse(results=results, model=engine.reranker_model_name)
