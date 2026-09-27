import asyncio
import time

import pytest

from contexta.workers.model_server import DynamicMicroBatcher, ModelServerError


@pytest.mark.asyncio
async def test_microbatch_shutdown_resolves_pending_futures():
    batcher = DynamicMicroBatcher(max_queue_size=4, max_batch_size=4)
    batcher.start()

    def slow_compute(texts):
        time.sleep(0.2)
        return [[0.0] for _ in texts]

    batcher._compute_batch = slow_compute
    tasks = [asyncio.create_task(batcher.embed_single(str(index))) for index in range(3)]
    await asyncio.sleep(0.02)
    await batcher.stop()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(task.done() for task in tasks)
    assert all(isinstance(result, ModelServerError) for result in results)
    assert batcher.pending_count == 0
    assert batcher.queue_size == 0


@pytest.mark.asyncio
async def test_microbatch_failure_resolves_every_future():
    batcher = DynamicMicroBatcher(max_queue_size=4, max_batch_size=4)
    batcher.start()

    def fail_compute(texts):
        raise RuntimeError("backend failed")

    batcher._compute_batch = fail_compute
    tasks = [asyncio.create_task(batcher.embed_single(str(index))) for index in range(3)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await batcher.stop()

    assert all(task.done() for task in tasks)
    assert all(isinstance(result, ModelServerError) for result in results)
    assert batcher.pending_count == 0
    assert batcher.queue_size == 0
