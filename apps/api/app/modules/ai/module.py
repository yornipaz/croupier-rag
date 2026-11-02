from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.ai.presentation.router import router

__all__ = ["build_ai_module", "build_ai_router", "router"]


def build_ai_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_ai_module(settings: Settings) -> APIRouter:
    return build_ai_router(settings)
