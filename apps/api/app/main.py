from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import build_container
from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.modules.ai.module import build_ai_router
from app.modules.chat.module import build_chat_router
from app.modules.documents.module import build_documents_router
from app.modules.health.module import build_health_router
from app.modules.ingestion.module import build_ingestion_router
from app.modules.retrieval.module import build_retrieval_router
from app.modules.vector_store.module import build_vector_store_router
from app.shared.exception_handlers import register_exception_handlers
from app.shared.logging import get_logger
from app.shared.middleware import RequestContextMiddleware

settings = get_settings()
configure_logging(settings)
logger = get_logger(__name__)

# Order is intentional: it drives the OpenAPI / Swagger tag order.
OPENAPI_TAGS: list[dict[str, Any]] = [
    {"name": "health", "description": "Readiness of Redis and Qdrant."},
    {"name": "documents", "description": "PDF upload, metadata and page crops."},
    {"name": "ingestion", "description": "Parsing, chunking and background jobs (SSE)."},
    {"name": "retrieval", "description": "Hybrid dense + sparse retrieval."},
    {"name": "chat", "description": "Grounded answers with citations and images."},
    {"name": "ai", "description": "LLM and embedding provider configuration."},
    {"name": "vector-store", "description": "Qdrant collection management."},
]

ROUTER_FACTORIES = (
    build_health_router,
    build_documents_router,
    build_ingestion_router,
    build_retrieval_router,
    build_chat_router,
    build_ai_router,
    build_vector_store_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = await build_container(settings)
    app.state.container = container
    logger.info(
        "app.started",
        env=settings.env,
        llm_provider=settings.llm_provider,
        llm_configured=settings.llm_configured,
        embedding_provider=settings.embedding_provider,
    )
    try:
        yield
    finally:
        await container.aclose()
        logger.info("app.stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Multimodal RAG for technical PDF manuals.",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(application)

    for factory in ROUTER_FACTORIES:
        application.include_router(factory(settings), prefix=settings.api_prefix)

    return application


app = create_app()
