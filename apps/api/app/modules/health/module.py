from __future__ import annotations

from fastapi import APIRouter
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.config.settings import Settings
from app.modules.health.application.use_cases.check_health import CheckHealthUseCase
from app.modules.health.infrastructure.probes import QdrantHealthProbe, RedisHealthProbe
from app.modules.health.presentation.router import get_check_health_use_case, router

__all__ = [
    "build_check_health_use_case",
    "build_health_module",
    "build_health_router",
    "get_check_health_use_case",
    "router",
]


def build_health_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py."""
    _ = settings
    return router


def build_health_module(settings: Settings) -> APIRouter:
    return build_health_router(settings)


def build_check_health_use_case(
    redis_client: Redis,
    qdrant_client: AsyncQdrantClient,
    settings: Settings,
) -> CheckHealthUseCase:
    """Composition root for the health probes (Redis + Qdrant, non-blocking)."""
    _ = settings
    return CheckHealthUseCase(
        [
            RedisHealthProbe(redis_client),
            QdrantHealthProbe(qdrant_client),
        ]
    )
