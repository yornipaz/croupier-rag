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
| Web | http://localhost:4200 |
| Health | http://localhost:8000/v1/health |
| Swagger UI | http://localhost:8000/v1/docs |
| OpenAPI | http://localhost:8000/v1/openapi.json |
| Qdrant dashboard | http://localhost:6333/dashboard |

Sin `.env` también arranca: la API responde y reporta el LLM como no configurado.

Servicios Docker: `api`, `worker`, `redis`, `qdrant`, `web`. La web se sirve con Nginx y
proxifica `/api/*` al backend (`/api/v1/...` → `http://api:8000/v1/...`), incluyendo SSE para
la línea de tiempo de ingesta. En desarrollo también puedes ejecutar `cd apps/web && npm start`;
arranca con `useMock: true` para probar el chat sin depender del LLM.

## Documentación

- [Arquitectura completa](docs/architecture.md): contenedores, módulos, contratos, flujos,
  proveedores de IA, operación y troubleshooting.
- [Diagramas interactivos](docs/diagrams/README.md): arquitectura, ingesta, consulta y ciclo de
  vida de un job como HTML autocontenido con temas, búsqueda, foco y vistas guiadas.
- [ADRs](docs/adr/README.md): decisiones de monolito modular, Qdrant híbrido y RRF.

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
│       ├── Dockerfile        # multi-stage: build + Nginx
│       └── nginx.conf        # SPA fallback + proxy /api y SSE
├── docs/
│   ├── architecture.md       # Documento principal de arquitectura
│   ├── adr/                  # Decisiones de arquitectura
│   └── diagrams/             # HTML interactivos + specs Archify
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
| `LLM_PROVIDER` | `gemini` | `gemini`, `ollama`, `openai` o `deepseek`. |
| `EMBEDDING_PROVIDER` | `fastembed` | `fastembed`, `ollama` o `gemini`. |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Modelo denso; con FastEmbed debe estar en `list_supported_models()`. |
| `SPARSE_EMBEDDING_LANGUAGE` | `spanish` | Idioma del stemmer/stopwords de BM25. |
| `GEMINI_API_KEY` | vacío | Necesaria con `LLM_PROVIDER=gemini` o `EMBEDDING_PROVIDER=gemini`. |
| `OPENAI_API_KEY` | vacío | Opcional, con `LLM_PROVIDER=openai`. |
| `DEEPSEEK_API_KEY` | vacío | Necesaria con `LLM_PROVIDER=deepseek`. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Endpoint OpenAI-compatible de DeepSeek. |
| `DEEPSEEK_THINKING_ENABLED` | `false` | Desactiva el modo thinking para respuestas RAG más rápidas. |
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
producción usa `environment.production.ts` con `useMock: false`, `apiBaseUrl: '/api'` y el
cliente HTTP real; el contenedor `web` sirve los estáticos y proxifica la API.

La UI incluye:

- **Figura junto a la respuesta**: miniatura con zoom y modal "Ver en la página"; carga el crop
  del PDF con `highlight=true`, skeleton, fallback a la imagen original, cierre con `Esc` y
  foco atrapado.
- **Biblioteca**: subida drag & drop solo PDF (máximo 50 MB), estado derivado, refresco y borrado
  con confirmación inline.
- **Línea de tiempo de ingesta**: SSE desde `/jobs/{id}/events`, etapas parsing → imágenes →
  chunking → embeddings → indexación, porcentaje, error legible, reconexión y cierre al terminal.
- **Inspector de recuperación**: activa “Modo auditor” para enviar `debug=true`; el drawer lista
  chunks, sección, página, scores, ranks denso/sparse y el motivo de rechazo cuando no hay
  respaldo documental.
- **Atajos**: `Enter` envía, `Shift+Enter` salta línea, `/` enfoca la consulta, `Ctrl/Cmd+K` crea
  conversación, `Esc` cierra modales/paneles y `?` abre la ayuda de teclado.
- Estados vacíos propios, transiciones sutiles y respeto a `prefers-reduced-motion`.

### Embeddings locales

Con `EMBEDDING_PROVIDER=fastembed` el modelo ONNX se carga una vez por proceso del worker y se
reutiliza entre jobs y reintentos. No requiere API key ni conexión a un proveedor externo.
`EMBEDDING_TIMEOUT_S` es el límite por lote, no por documento: un manual grande puede tardar
varios minutos en CPU (por ejemplo, 98 páginas / 190 chunks ≈ 5 min). Si cambias variables del
`.env`, recrea el worker con `docker compose up -d --force-recreate worker`; `restart` no vuelve
a leer `env_file`.

### Usar DeepSeek para el chat

DeepSeek expone una API compatible con OpenAI Chat Completions. El backend incluye un adapter
`DeepSeekLLM`; para cambiar solo el chat (las embeddings siguen siendo locales con FastEmbed):

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_THINKING_ENABLED=false
EMBEDDING_PROVIDER=fastembed
```

`deepseek-flash` es el id oficial de DeepSeek para DeepSeek-V4.1-Flash. Si usas un gateway
distinto (por ejemplo Cloudflare), cambia `DEEPSEEK_BASE_URL` y `LLM_MODEL` por los de ese
proveedor. Después recrea la API para que lea el `.env`:

```bash
docker compose up -d --force-recreate api
```

En los logs de arranque de la API debe aparecer `llm_provider=deepseek llm_configured=True`. Si el
endpoint o la clave son incorrectos, el chat devuelve un error tipado y no filtra la traza del
proveedor.

## Endpoints actuales

Rutas relativas a `API_PREFIX`; el `.env` de demostración usa `/v1`.

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

`POST /chat/ask` necesita un proveedor LLM configurado (`GEMINI_API_KEY`, `OPENAI_API_KEY`,
`DEEPSEEK_API_KEY` u Ollama). Sin LLM, el guard de baja relevancia sigue respondiendo "No tengo información suficiente…"
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
