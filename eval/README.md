# Evaluación

Harness reproducible para comparar versiones del RAG sobre un manual técnico.

## Dataset

- `golden.draft.json`: borrador generado a partir de `Manual de usuario app.pdf`.
- `golden.json`: dataset revisado y definitivo (renombrar el borrador cuando esté validado).

Cada caso usa este contrato:

```json
{
  "id": "text-01",
  "question": "¿En qué lenguaje está desarrollada la aplicación?",
  "expected_pages": [3],
  "needs_figure": false,
  "should_refuse": false,
  "notes": "La página 3 indica Node.js."
}
```

`expected_pages` es 1-based. En preguntas de rechazo va vacío y `should_refuse=true`.

## Ejecución

```bash
make eval-baseline   # guarda eval/results/baseline.json
make eval            # guarda eval/results/latest.json
make eval-compare    # compara latest contra baseline
```

Variables: `DEMO_PDF` (ruta del PDF, admite espacios) y `API_URL` (default
`http://localhost:8000`; el script detecta `API_PREFIX`/`/v1` automáticamente).

El script sube el PDF si hace falta (`--ensure-doc`) y espera a que el job de
ingesta quede `COMPLETED`.

## Métricas

| Dimensión | Métrica |
| --- | --- |
| Recuperación | `hit@k`: alguna `expected_pages` entre las fuentes devueltas |
| Contexto visual | `figure_hit`: respuesta con imagen para casos `needs_figure` |
| Defensividad | `refusal_correct`: `should_refuse` coincide con `sufficient=false` |
| Coste | media y p95 de `contextTokens`, `promptTokens`, `chunksSent` |
| Uso del LLM | tasa de `llmCalled` |
| Latencia | p50 y p95 de `usage.latencyMs` |

`usage` de `POST /chat/ask` usa los metadatos del proveedor cuando existen. Si
no, estima tokens con `count_tokens` (palabras y signos como unidades), el mismo
contador que usa el chunker. Un rechazo sin llamada al LLM reporta
`llmCalled=false` y `completionTokens=0`.
