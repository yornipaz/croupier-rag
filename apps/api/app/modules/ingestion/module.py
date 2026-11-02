from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.ingestion.presentation.router import router

__all__ = ["build_ingestion_module", "build_ingestion_router", "router"]


def build_ingestion_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_ingestion_module(settings: Settings) -> APIRouter:
    return build_ingestion_router(settings)
