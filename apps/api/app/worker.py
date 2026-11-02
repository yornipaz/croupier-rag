from __future__ import annotations

from celery import Celery

from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "croupier",
    broker=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
    worker_prefetch_multiplier=1,
)
