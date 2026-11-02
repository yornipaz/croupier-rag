# Proyecto: RAG Multimodal para manuales técnicos en PDF

## Objetivo

Sistema que ingiere PDFs técnicos (texto, tablas, diagramas), los indexa y responde preguntas en lenguaje
natural mostrando respuesta + fuente (archivo, página) + la imagen/diagrama relevante.
Es una prueba técnica: se evalúa arquitectura limpia, asincronía, resiliencia, integración robusta de IA,
UX del contexto visual y creatividad. Debe levantar con `docker compose up`.

## Stack (no cambiar sin pedirlo)

- apps/api: Python 3.12, FastAPI, Pydantic v2 + pydantic-settings, Celery + Redis, qdrant-client + fastembed,
  PyMuPDF, httpx, tenacity, structlog, sse-starlette, google-genai. Calidad: pytest, pytest-asyncio, respx,
  ruff, mypy --strict, import-linter. Gestor: uv.
- apps/web: Angular (última estable), standalone components, signals, Tailwind, ngx-markdown.
- Infra: docker-compose con api, worker, redis, qdrant, web; ollama bajo profile opcional.

## Arquitectura: monolito modular + hexagonal por módulo

apps/api/app/modules/<modulo>/{domain,application/{ports,use_cases,dto},infrastructure,presentation/{router.py,schemas.py}}/module.py
Módulos: documents, ingestion, ai, vector_store, retrieval, chat, health. Transversal en app/shared y app/config.
Reglas obligatorias:

1. `domain` es Python puro: sin imports de FastAPI, Celery, qdrant, fitz ni librerías externas (solo stdlib y pydantic opcional).
2. Los casos de uso dependen SOLO de puertos (typing.Protocol o ABC). Nunca de adapters.
3. Un módulo solo importa puertos/DTOs públicos de otro, jamás sus adapters. Se valida con import-linter (`make lint-arch`).
4. Cada caso de uso = un archivo, una responsabilidad (SOLID).
5. El proveedor concreto se elige en module.py con factories según env (LLM_PROVIDER, EMBEDDING_PROVIDER...).
   La inyección va por `Depends` apuntando a funciones de composition root; los tests usan `app.dependency_overrides`.
6. Cada adapter externo (LLM, embeddings, vector store) se envuelve con decorador de resiliencia:
   timeout explícito, retry (tenacity) con backoff exponencial + jitter SOLO para 429/5xx/timeouts, y circuit breaker propio.
7. Errores tipados (AppError con code, http_status, retryable) + exception handler global; nunca filtrar trazas al cliente.
8. Configuración solo vía Settings validado al arrancar (falla rápido). Mantener .env.example completo.
9. Todo I/O es async. El trabajo CPU-bound (PyMuPDF, fastembed) corre en el worker Celery o con asyncio.to_thread.
10. JSON de la API en camelCase (alias_generator=to_camel, populate_by_name=True).

## Contratos clave

- ParsedDocument (puerto DocumentParser): pages[{number,width,height,blocks[{type:'text'|'table'|'image',bbox:[x0,y0,x1,y1],
  text?,font_size?,is_bold?,image_id?}]}]. Imágenes en DATA_DIR/images/{doc_id}/{image_id}.png. Coordenadas en puntos PDF, origen arriba-izquierda.
- Chunk: {id(uuid5 determinista), doc_id, page, bbox, section_path, kind:'text'|'table'|'caption', text, image_ids[], token_count}.
- Job: {job_id, doc_id, status:'PENDING'|'PROCESSING'|'COMPLETED'|'FAILED', stage, progress(0-100), error?}.
  El estado vive en Redis; el progreso se publica por Redis pub/sub y la API lo retransmite por SSE (el worker es otro proceso).
- POST /documents → 202 {jobId, documentId}. GET /jobs/{id}. GET /jobs/{id}/events (SSE).
- POST /chat/ask → {answer, sufficient, sources[{file,page,bbox,sectionPath}], images[{url,page,bbox}], debug?{retrieved[],denseRank,sparseRank,rrfScore}}.
- GET /documents/{id}/pages/{n}/crop?bbox=x0,y0,x1,y1&highlight=true → PNG (PyMuPDF get_pixmap con clip + rect resaltado).

## RAG: reglas

- Chunking por layout: encabezados por tamaño de fuente → section_path; tablas = chunk completo; si excede el máximo se divide por párrafo/frase, nunca por caracteres.
- Vinculación imagen↔texto: 1) captions por regex (Figura/Fig. N), 2) referencias "ver Figura N", 3) fallback por distancia vertical de bbox en la misma página.
- Recuperación híbrida: denso + sparse BM25 (fastembed) con Prefetch + FusionQuery RRF del Query API de Qdrant; filtro opcional por doc_id.
- Generación defensiva: si el mejor score < umbral → "No tengo información suficiente..." SIN llamar al LLM.
  El prompt exige usar solo el contexto, citar [S1], [S2], declarar cuando falte info e ignorar instrucciones dentro del contexto.
  Salida JSON validada con Pydantic {answer, used_sources[], sufficient}.

## Calidad

- pytest: fakes en memoria de LLMPort/EmbeddingPort/VectorStorePort/JobRepository; tests de chunkers, ImageLinker, CircuitBreaker,
  retry (simular 429, timeout, breaker abierto), caso "sin información suficiente", y API con TestClient + dependency_overrides.
  HTTP externo mockeado con respx. Sin red en tests.
- Logging estructurado (structlog) con request_id y job_id en toda operación crítica.
- Commits convencionales (feat:, fix:, test:, refactor:, docs:, chore:). Un commit lógico por tarea.

## Cómo trabajar

- Antes de codificar: usa Context7 para verificar APIs de FastAPI, Celery, qdrant-client, fastembed, tenacity, PyMuPDF y Angular. No inventes métodos.
- En modo Plan: lista archivos a crear/modificar y espera confirmación.
- No agregues dependencias ni features fuera de lo pedido. Si algo es ambiguo, pregunta.
- Al terminar cada tarea: corre ruff, mypy, lint-arch y pytest; reporta resultados y sugiere el mensaje de commit.
