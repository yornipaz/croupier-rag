from __future__ import annotations

from celery import Celery

from app.config.settings import get_settings

INGESTION_TASK_NAME = "ingestion.ingest_document"

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
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=settings.ingestion_time_limit_s,
    task_soft_time_limit=settings.ingestion_soft_time_limit_s,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
    worker_prefetch_multiplier=1,
)
