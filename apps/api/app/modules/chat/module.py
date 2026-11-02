from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.chat.presentation.router import router

__all__ = ["build_chat_module", "build_chat_router", "router"]


def build_chat_router(settings: Settings) -> APIRouter:
    """Factory consumed by main.py; adapters/use cases are wired in later phases."""
    _ = settings
    return router


def build_chat_module(settings: Settings) -> APIRouter:
    return build_chat_router(settings)
