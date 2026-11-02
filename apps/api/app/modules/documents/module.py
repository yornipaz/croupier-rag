from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.documents.presentation.router import router

__all__ = ["build_documents_module", "build_documents_router", "router"]


def build_documents_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_documents_module(settings: Settings) -> APIRouter:
    return build_documents_router(settings)
