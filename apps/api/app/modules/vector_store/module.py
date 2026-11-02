from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.vector_store.presentation.router import router

__all__ = ["build_vector_store_module", "build_vector_store_router", "router"]


def build_vector_store_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_vector_store_module(settings: Settings) -> APIRouter:
    return build_vector_store_router(settings)
