"""Celery application configuration.

Configures the Celery app with Redis as the broker and result backend.
All worker tasks are auto-discovered from the contexta.workers package.
"""

from celery import Celery

from contexta.config.settings import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application instance."""
    settings = get_settings()

    app = Celery(
        "contexta",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )

    app.conf.update(
        # Serialization
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",

        # Task behavior
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=True,
        worker_prefetch_multiplier=1,

        # Result expiration (1 hour)
        result_expires=3600,

        # Task routing
        task_routes={
            "contexta.workers.extraction_tasks.*": {"queue": "extraction"},
            "contexta.workers.embedding_tasks.*": {"queue": "embedding"},
            "contexta.workers.decay_tasks.*": {"queue": "maintenance"},
            "contexta.workers.reflection_tasks.*": {"queue": "maintenance"},
            "contexta.workers.dream_tasks.*": {"queue": "maintenance"},
        },

        # Auto-discover tasks in the workers package
        include=[
            "contexta.workers.extraction_tasks",
            "contexta.workers.embedding_tasks",
            "contexta.workers.decay_tasks",
            "contexta.workers.reflection_tasks",
            "contexta.workers.dream_tasks",
        ],

        beat_schedule={
            "daily-decay-cycle": {
                "task": "contexta.workers.decay_tasks.run_decay_cycle",
                "schedule": 86400.0,
            },
            "nightly-reflection-cycle": {
                "task": "contexta.workers.reflection_tasks.run_reflection_cycle",
                "schedule": 86400.0,
            },
            "weekly-dream-cycle": {
                "task": "contexta.workers.dream_tasks.run_dream_cycle",
                "schedule": 604800.0,
            },
        },

        # Timezone
        timezone="UTC",
        enable_utc=True,
    )

    return app


# Module-level Celery app instance used by workers and task producers
celery_app = create_celery_app()
