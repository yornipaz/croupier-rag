from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.config.settings import Settings
from app.modules.documents.module import DocumentServices, build_document_services
from app.modules.health.application.use_cases.check_health import CheckHealthUseCase
from app.modules.health.module import build_check_health_use_case
from app.modules.ingestion.module import IngestionServices, build_ingestion_services


@dataclass
class Container:
    """Composition root: the only place that knows concrete adapters."""

    settings: Settings
    redis: Redis
    qdrant: AsyncQdrantClient
    check_health: CheckHealthUseCase
    ingestion: IngestionServices
    documents: DocumentServices

    async def aclose(self) -> None:
        await self.redis.aclose()
        await self.qdrant.close()


async def build_container(settings: Settings) -> Container:
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=int(settings.vector_store_timeout_s),
    )
    ingestion = build_ingestion_services(settings, redis_client)
    documents = build_document_services(
        settings,
        qdrant=qdrant_client,
        job_repository=ingestion.job_repository,
    )

    return Container(
        settings=settings,
        redis=redis_client,
        qdrant=qdrant_client,
        check_health=build_check_health_use_case(redis_client, qdrant_client, settings),
        ingestion=ingestion,
        documents=documents,
    )
