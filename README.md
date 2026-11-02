# Croupier RAG

RAG multimodal para manuales técnicos en PDF: ingestión de texto, tablas y diagramas, recuperación
híbrida y respuestas con fuente (archivo, página, bbox) e imagen relevante.

> **Estado: pipeline RAG completo + UI Angular.** La API sube PDFs, los procesa en el worker
> (texto, tablas, imágenes y captions), indexa chunks híbridos en Qdrant, recupera contexto con
> fuentes e imágenes y responde con citas validadas. La web incluye modo demo con `useMock`.

## Arranque (Docker)

Requisitos: Docker 24+ con Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

| Recurso | URL |
| --- | --- |
| Health | http://localhost:8000/health |
| Swagger UI | http://localhost:8000/docs |
| OpenAPI | http://localhost:8000/openapi.json |
| Qdrant dashboard | http://localhost:6333/dashboard |

Sin `.env` también arranca: la API responde y reporta el LLM como no configurado.

Servicios Docker: `api`, `worker`, `redis`, `qdrant`. La web Angular se ejecuta con
`cd apps/web && npm start`; en desarrollo arranca con `useMock: true` para probar el chat sin
depender del LLM.

## Estructura

```text
.
├── apps/
│   ├── api/                  # FastAPI + Celery
│   │   ├── app/
│   │   │   ├── config/       # Settings + logging
│   │   │   ├── shared/       # Errores, middleware, camelCase, resiliencia
│   │   │   ├── modules/      # 7 módulos hexagonales
│   │   │   ├── bootstrap.py  # Composition root
│   │   │   ├── main.py       # create_app()
│   │   │   └── worker.py     # Celery
│   │   ├── tests/
│   │   ├── Dockerfile        # multi-stage
│   │   └── .importlinter
│   └── web/                  # Angular 22 + signals + Tailwind
├── docs/adr/                 # Decisiones de arquitectura
├── eval/                     # Plan del conjunto de evaluación
├── docker-compose.yml
├── Makefile
└── .env.example
```

Cada módulo sigue `domain / application{ports,use_cases,dto} / infrastructure / presentation /
module.py`. `module.py` expone `router` y las factories de composición.

## Configuración

Todo se valida al arrancar con Pydantic Settings. Base: `.env`; override por ambiente:
`.env.${ENV}` (por ejemplo `.env.production`). Las variables de proceso tienen prioridad.

Variables principales:

| Variable | Default | Descripción |
| --- | --- | --- |
| `ENV` | `local` | Selecciona `.env.${ENV}`. |
| `API_PREFIX` | vacío | Prefijo común; si se define, usar `/v1/health`, etc. |
| `REDIS_URL` | `redis://localhost:6379/0` | Estado de jobs y broker Celery. |
| `QDRANT_URL` | `http://localhost:6333` | Vector store. |
| `DATA_DIR` | `./data` | PDFs, metadatos, imágenes extraídas y caché de crops. |
| `LLM_PROVIDER` | `gemini` | `gemini`, `ollama` u `openai`. |
| `EMBEDDING_PROVIDER` | `fastembed` | `fastembed`, `ollama` o `gemini`. |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Modelo denso; con FastEmbed debe estar en `list_supported_models()`. |
| `SPARSE_EMBEDDING_LANGUAGE` | `spanish` | Idioma del stemmer/stopwords de BM25. |
| `GEMINI_API_KEY` | vacío | Necesaria con `LLM_PROVIDER=gemini` o `EMBEDDING_PROVIDER=gemini`. |
| `OPENAI_API_KEY` | vacío | Opcional, con `LLM_PROVIDER=openai`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama local. |
| `RETRIEVAL_MIN_SCORE` | `0.30` | Umbral defensivo sobre similitud densa; si no se alcanza, chat no llama al LLM. |
| `CHAT_HISTORY_TURNS` | `6` | Pares de turnos previos usados para reescribir y responder. |
| `CHUNK_MAX_TOKENS` | `450` | Tamaño máximo de chunk. |
| `LLM_TIMEOUT_S` | `60` | Timeout por intento. |
| `BREAKER_FAILURE_THRESHOLD` | `5` | Fallos antes de abrir el circuito. |
| `BREAKER_RECOVERY_S` | `30` | Espera antes de half-open. |

`.env.example` documenta el resto.

## Calidad

```bash
make test        # pytest (CircuitBreaker, retry, settings, health, API)
make lint        # ruff
make mypy        # mypy --strict
make lint-arch   # import-linter (reglas 1 y 3)
make quality     # todo
```

Los tests no usan red: health se prueba con probes fake y `dependency_overrides`.

## Web

```bash
cd apps/web
npm install
npm start          # http://localhost:4200/chat
npm run gen:api    # tipos desde OpenAPI
npm run lint
npm run build
```

En desarrollo (`environment.ts`) `useMock: true` permite chatear sin backend: incluye una
respuesta con fuentes e imagen y otra con estado "sin información suficiente". El build de
producción usa `environment.production.ts` con `useMock: false` y el cliente HTTP real.

## Endpoints actuales

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Redis + Qdrant en paralelo con timeout; `503` si algo crítico falla. |
| `POST` | `/documents` | Multipart PDF; responde `202 {jobId, documentId}`. |
| `GET` | `/documents` | Lista de documentos con metadatos y conteos. |
| `GET` | `/documents/{id}` | Metadatos de un documento. |
| `DELETE` | `/documents/{id}` | Borra vectores, PDF, imágenes, caché y job. |
| `GET` | `/documents/{id}/pages/{n}/crop` | PNG recortado por `bbox`; `highlight=true` resalta la zona. |
| `GET` | `/jobs/{id}` | Estado, etapa, progreso y error del job. |
| `GET` | `/jobs/{id}/events` | SSE con estado actual y actualizaciones del job. |
| `POST` | `/retrieval/search` | Búsqueda híbrida; devuelve chunks, imágenes, `topScore` y `debug` opcional. |
| `POST` | `/chat/ask` | Respuesta defensiva con fuentes citadas e imágenes; `?debug=true` añade trazas. |
| `GET` | `/docs` | Swagger UI ordenada por tags. |

`POST /chat/ask` necesita un proveedor LLM configurado (`GEMINI_API_KEY`, `OPENAI_API_KEY` u
Ollama). Sin LLM, el guard de baja relevancia sigue respondiendo "No tengo información suficiente…"
sin invocarlo; una consulta con contexto devuelve `503 llm_not_configured`.

La primera ingesta descarga el modelo denso de FastEmbed en el worker; en Docker queda cacheado en
el volumen `data` (`/data/cache`). La API reutiliza la misma caché para retrieval.

## Resiliencia (lista para usar)

`app/shared/resilience` expone:

- `retry(...)`: backoff exponencial + jitter, solo errores retryables (429/5xx/timeouts/transporte).
- `CircuitBreaker`: `CLOSED → OPEN → HALF_OPEN`, umbral y recuperación configurables.
- `resilient(...)`: decorador que compone timeout + retry + breaker.

```python
breaker = CircuitBreaker("gemini", failure_threshold=5, recovery_timeout=30)

@resilient(name="gemini", breaker=breaker, timeout_s=60)
async def generate(prompt: str) -> str: ...
```

`ai/module.py` envuelve los adapters de LLM/embeddings y `vector_store/module.py` envuelve el
adapter de Qdrant. Así el puerto que consume retrieval/chat ya incluye timeout, retry y breaker.

## Roadmap

1. ✅ `documents`: upload, metadata y crop con PyMuPDF.
2. ✅ `ingestion`: parser por bloques, chunking por layout, ImageLinker y jobs SSE.
3. ✅ `ai` + `vector_store`: Gemini/Ollama/fastembed y Qdrant híbrido con RRF.
4. ✅ `retrieval` + `chat`: umbral defensivo, citas `[S1]` y salida JSON validada.
5. ✅ `apps/web`: Angular standalone + signals + Tailwind, modo demo y temas claro/oscuro.
6. Opcional: `POST /chat/ask/stream` con SSE incremental.
