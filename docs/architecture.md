# Arquitectura de Croupier RAG

Croupier RAG es un sistema multimodal para consultar manuales técnicos en PDF. Extrae texto,
tablas, diagramas y captions, los indexa en Qdrant y responde preguntas con fuente, página, bbox e
imagen relevante. La ingesta es asíncrona; el chat es defensivo y solo llama al LLM cuando la
recuperación supera el umbral configurado.

## Mapa de documentación

| Documento | Contenido |
| --- | --- |
| [Diagrama de arquitectura](diagrams/architecture.html) | Contenedores, límites y flujos principales |
| [Flujo de ingesta](diagrams/ingestion-workflow.html) | PDF → parse → chunks → embeddings → Qdrant |
| [Secuencia de consulta](diagrams/chat-sequence.html) | Pregunta → retrieval → guard → LLM → fuentes |
| [Ciclo de vida del job](diagrams/job-lifecycle.html) | `PENDING`, etapas, retry, `COMPLETED` y `FAILED` |
| [ADRs](adr/README.md) | Decisiones de monolito modular, Qdrant y RRF |

Los diagramas son HTML autocontenidos: tienen temas claro/oscuro, búsqueda, foco, trazado de
relaciones, vistas guiadas y exportación. Los specs editables están en `docs/diagrams/src/`.

## Arranque

```bash
cp .env.example .env
docker compose up --build
```

| Recurso | URL por defecto |
| --- | --- |
| Web | http://localhost:4200 |
| API health | http://localhost:8000/v1/health |
| Swagger | http://localhost:8000/v1/docs |
| Qdrant | http://localhost:6333/dashboard |

Servicios: `web`, `api`, `worker`, `redis`, `qdrant`. Ollama es opcional y no está en el perfil por
defecto. El prefijo real de la API depende de `API_PREFIX`; el `.env` de demostración usa `v1`.

## Contexto y contenedores

```text
Navegador
  └─ web (Angular + Nginx, :4200)
       └─ /api/* ──► api (FastAPI, :8000)
                      ├─ Redis: jobs, SSE, historial
                      ├─ Qdrant: chunks densos + BM25
                      ├─ data/: PDFs, imágenes, crops
                      ├─ FastEmbed: embeddings locales
                      └─ DeepSeek API: respuesta del chat

api ──► Redis ──► worker (Celery, 2 procesos)
worker ──► data/, FastEmbed, Qdrant
worker ──► Redis: estado/progreso
```

- La web se sirve como SPA y Nginx proxifica `/api/` al backend. El proxy mantiene SSE sin
  buffering y acepta PDFs de hasta 60 MB.
- La API no ejecuta PyMuPDF ni FastEmbed durante el request de subida. Solo crea el job y responde
  `202`.
- El worker es el proceso CPU-bound. Redis es el estado compartido y el canal de eventos.
- Qdrant guarda el índice híbrido de chunks. El volumen `data` es la fuente de PDFs, imágenes y
  crops cacheados.
- DeepSeek es el proveedor LLM de chat del entorno actual. Gemini, OpenAI y Ollama siguen
  disponibles por configuración. Los embeddings son locales con FastEmbed.

## Backend: monolito modular + hexagonal

Cada módulo vive en `apps/api/app/modules/<modulo>/`:

```text
domain/                  Reglas puras; sin FastAPI, Celery, Qdrant ni fitz
application/
  ports/                 Protocols/ABCs que consume el caso de uso
  use_cases/             Una responsabilidad por archivo
  dto/                   Contratos internos
infrastructure/          Adapters: PyMuPDF, FastEmbed, Qdrant, Redis, LLMs
presentation/            router.py + schemas.py
module.py                Composition root local
```

| Módulo | Responsabilidad |
| --- | --- |
| `documents` | Metadatos, almacenamiento de PDFs, listado, borrado y crop de páginas |
| `ingestion` | Parser por layout, chunking, ImageLinker, pipeline y jobs/SSE |
| `ai` | Puertos y adapters de LLM/embeddings; resiliencia del proveedor |
| `vector_store` | Indexación y búsqueda híbrida en Qdrant; BM25 sparse |
| `retrieval` | Recuperación de contexto, imágenes y scores de ranking |
| `chat` | Historial, prompt defensivo, validación de JSON/citas y respuesta |
| `health` | Probes de Redis y Qdrant en paralelo |

Reglas que se validan con `import-linter`:

1. `domain` es Python puro.
2. Los casos de uso dependen de puertos, nunca de adapters.
3. Un módulo solo importa puertos/DTOs públicos de otro.
4. Los adapters se eligen en `module.py`; los tests usan `dependency_overrides`.
5. Los errores son `AppError` tipados; el handler global no filtra trazas.

## Contratos principales

### ParsedDocument

```text
pages[]:
  number, width, height
  blocks[]:
    type: text | table | image
    bbox: [x0, y0, x1, y1]   # puntos PDF, origen arriba-izquierda
    text?, font_size?, is_bold?, image_id?
```

Las imágenes se guardan en `DATA_DIR/images/{doc_id}/{image_id}.png`; los metadatos laterales
permiten reconstruir página/bbox en retrieval.

### Chunk

```text
{ id, doc_id, page, bbox, section_path, kind: text|table|caption,
  text, image_ids[], token_count }
```

`id` es un UUID5 determinista. Los chunks conservan la sección y los ids de imagen vinculados.

### Job

```text
{ job_id, doc_id, status: PENDING|PROCESSING|COMPLETED|FAILED,
  stage, progress: 0..100, error?, updated_at }
```

El estado vive en Redis. El worker publica eventos; la API los retransmite por SSE. El cliente
puede reconectar y recibe el estado actual al abrir el stream.

## Flujo de ingesta

1. `POST /documents` valida el PDF y responde `202 {jobId, documentId}`.
2. El job queda en Redis y Celery lo entrega a un worker.
3. El pipeline reporta progreso por etapas:

| Etapa | Progreso | Trabajo |
| --- | --- | --- |
| `parse` | 0–25 | PyMuPDF: texto, tablas, imágenes y bbox |
| `detect_structure` | 25–40 | Encabezados y `section_path` |
| `link_images` | 40–50 | Captions, referencias “ver Figura N” y proximidad |
| `chunk` | 50–65 | Chunks por layout; tablas completas |
| `embed` | 65–85 | FastEmbed denso + BM25 sparse por lotes |
| `index` | 85–98 | Upsert híbrido en Qdrant |
| `completed` | 100 | Metadatos de páginas/chunks persistidos |

- El worker precarga y reutiliza el modelo FastEmbed por proceso. El modelo se cachea en
  `/data/cache/fastembed`; no requiere API key.
- `EMBEDDING_TIMEOUT_S=90` es el límite **por lote**, no por documento. Un manual de 98 páginas
  puede tardar varios minutos en CPU.
- Si un error es retryable, Celery reintenta con backoff. Si no, el job termina en `FAILED` con
  etapa y mensaje legible.
- La API nunca marca el documento como listo antes de que el upsert termine.

## Flujo de consulta

1. La web envía `POST /chat/ask` con query, historial, `docId` opcional y `debug` opcional.
2. La API carga historial de Redis, reescribe la consulta si hay turnos previos y ejecuta
   retrieval híbrido.
3. Qdrant combina prefetch denso y BM25 con `FusionQuery` RRF. `top_score` es la similitud densa
   del mejor chunk.
4. **Guard defensivo:** si `top_score < RETRIEVAL_MIN_SCORE`, responde
   `INSUFFICIENT_ANSWER` y no llama al LLM.
5. Si hay evidencia, se construye el prompt con contexto `[S1]`, `[S2]`… y reglas anti-inyección.
6. El adapter LLM devuelve JSON; el parser valida `answer`, `used_sources` y `sufficient`.
   - Si el JSON es inválido, se intenta una reparación.
   - Si no hay citas válidas, se degrada a insuficiente.
7. La respuesta incluye solo fuentes e imágenes citadas. `debug=true` añade chunks, ranks y scores.
8. `FigureViewer` pide el crop con `highlight=true`; el modal permite zoom, fallback y cierre con
   `Esc`.

Detalle de endpoints:

| Método | Ruta | Uso |
| --- | --- | --- |
| `POST` | `/documents` | Subida multipart; `202` |
| `GET` | `/documents` | Biblioteca con conteos |
| `GET` | `/documents/{id}` | Metadatos |
| `DELETE` | `/documents/{id}` | Borra vectores, PDF, imágenes y job |
| `GET` | `/documents/{id}/pages/{n}/crop` | PNG por bbox; `highlight=true` |
| `GET` | `/jobs/{id}` | Estado actual |
| `GET` | `/jobs/{id}/events` | SSE de progreso |
| `POST` | `/retrieval/search` | Búsqueda híbrida con `topScore`/debug |
| `POST` | `/chat/ask?debug=true` | Respuesta defensiva + trazas |

## Frontend

`apps/web` usa Angular standalone, signals, Tailwind y `ngx-markdown`:

- `core/api`: contrato `ChatApi` con `HttpChatApi` y `MockChatApi`.
- `core/services`: documentos, tema, auditor, atajos.
- `core/sse`: servicio SSE de jobs con reconexión y cierre terminal.
- `features/chat`: historial, composer, Markdown, FigureViewer y estados de pensamiento/error.
- `features/documents`: drag & drop, validación, timeline y biblioteca.
- `features/inspector`: drawer del modo auditor con chunks/ranks/motivo de rechazo.
- `shared/ui`: iconos, focus trap, source chips y diálogo de atajos.

En desarrollo `environment.ts` usa `useMock: true`; producción usa `useMock: false` y
`apiBaseUrl: '/api'` detrás de Nginx. El modo auditor envía `debug=true` y separa “modo activo” de
“drawer abierto” para poder preguntar con trazas y abrir el inspector después.

## Proveedores de IA

| Variable | Valores | Uso |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `fastembed`, `ollama`, `gemini` | Embeddings; por defecto local |
| `LLM_PROVIDER` | `gemini`, `ollama`, `openai`, `deepseek` | Redacción del chat |

### DeepSeek

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_THINKING_ENABLED=false
EMBEDDING_PROVIDER=fastembed
```

`deepseek-flash` es el id oficial de DeepSeek para DeepSeek-V4.1-Flash. El adapter:
- usa Chat Completions compatible con OpenAI;
- desactiva thinking por defecto para reducir latencia;
- usa `response_format={"type":"json_object"}` cuando se le pasa un esquema, porque Chat
  Completions no acepta `json_schema` en la respuesta final;
- mantiene el timeout, retry y circuit breaker de `ResilientLLM`.

Si usas un gateway distinto (Cloudflare, etc.), cambia `DEEPSEEK_BASE_URL` y `LLM_MODEL` por los
del proveedor. Después de tocar `.env`, recrea la API; `restart` no recarga `env_file`:

```bash
docker compose up -d --force-recreate api
```

## Configuración relevante

| Variable | Default | Nota |
| --- | --- | --- |
| `API_PREFIX` | vacío | `.env` local usa `v1` |
| `DATA_DIR` | `./data` | En Docker: `/data` |
| `EMBEDDING_PROVIDER` | `fastembed` | No requiere key |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 768 dims |
| `EMBEDDING_TIMEOUT_S` | `90` | Por lote; CPU-bound |
| `EMBED_BATCH_SIZE` | `32` | Chunks por llamada |
| `RETRIEVAL_MIN_SCORE` | `0.30` | Guard defensivo |
| `CHUNK_MAX_TOKENS` | `450` | Chunking por layout |
| `MAX_UPLOAD_MB` | `50` | Validación de subida |
| `LLM_TIMEOUT_S` | `60` | Por intento |
| `HTTP_MAX_RETRIES` | `3` | Retry de adapters |
| `INGESTION_SOFT_TIME_LIMIT_S` | `600` | Límite Celery |

## Resiliencia y observabilidad

- `retry` con backoff exponencial + jitter solo para 429/5xx/timeouts/transporte.
- `CircuitBreaker` `CLOSED → OPEN → HALF_OPEN` por proveedor.
- `resilient` compone timeout + retry + breaker en LLM, embeddings y Qdrant.
- Logs estructurados `structlog` con `request_id` y `job_id`.
- Errores tipados: `code`, `http_status`, `retryable`; nunca se expone la traza del proveedor.
- SSE se reconecta con backoff y cierra al recibir `COMPLETED`/`FAILED`.
- FastEmbed se precarga en `worker_process_init`; se reutiliza entre jobs y reintentos.

## Seguridad y límites

- El contexto del PDF se trata como datos no confiables; el prompt ignora instrucciones internas.
- Las citas se filtran contra los chunks realmente recuperados.
- El crop solo acepta bbox dentro de la página; el renderer recorta y aplica el highlight.
- No se envían PDFs completos al LLM: solo los chunks recuperados.
- Las claves viven en `.env`/variables de entorno, nunca en el repositorio.
- `DATA_DIR`, Redis y Qdrant no están pensados para exposición pública; en producción deben ir en
  una red privada con auth/TLS.

## Troubleshooting

### `LLM is not configured for chat`

El contenedor no ve la clave del proveedor. Revisa:

```bash
docker exec croupier-rag-api-1 env | grep -E 'LLM_PROVIDER|LLM_MODEL|DEEPSEEK_API_KEY'
```

La key debe estar en `DEEPSEEK_API_KEY`, no en `GEMINI_API_KEY`, y hay que recrear:

```bash
docker compose up -d --force-recreate api
```

### `embedding:fastembed ... timed out`

No es una API key. Es un timeout local de embeddings. Revisa:
- que `EMBEDDING_TIMEOUT_S` sea al menos `90`;
- que el worker haya sido recreado después de cambiar `.env`;
- que el documento no sea enorme; si lo es, espera varios minutos o usa un modelo más pequeño.

### `LLM_PROVIDER` inválido

El valor es el proveedor (`deepseek`), no el modelo. El modelo va en `LLM_MODEL`
(`deepseek-flash`).

## Calidad

```bash
cd apps/api && uv run ruff check .
cd apps/api && uv run mypy app
cd apps/api && uv run lint-imports
cd apps/api && uv run pytest
cd apps/web && npm run build
cd apps/web && npm run lint
```

La suite backend cubre chunkers, ImageLinker, parser, pipeline, Qdrant, retrieval, chat, resiliencia,
jobs, health, settings y los adapters/proveedores. La web se verifica con `ng build` y lint.

## Diagramas interactivos

Los artefactos se generan con Archify y se validan en perfil `showcase` (9 checks de artefacto,
0 errores/0 warnings de composición). Los receipts y capturas de `visual-check` se generan como
sidecars locales; no son necesarios para abrir el HTML.

Para regenerar:

```bash
ARCHIFY=~/.agents/skills/archify/bin/archify.mjs
node $ARCHIFY validate architecture docs/diagrams/src/architecture.json --quality showcase
node $ARCHIFY deliver architecture docs/diagrams/src/architecture.json docs/diagrams/architecture.html --quality showcase
```

Repite con `workflow`, `sequence` y `lifecycle` usando los nombres de `docs/diagrams/src/`. Los
diagramas incluyen navegación, búsqueda, foco, temas y exportación sin necesitar el servidor de
Croupier.
