# Evaluación

Harness reproducible para comparar versiones del RAG sobre un manual técnico.

## Dataset

- `golden.draft.json`: borrador principal, con `split` (`calibration` / `test`).
- `golden.extra.draft.json`: 10 preguntas nuevas propuestas, pendientes de revisión.
- `golden.json`: dataset definitivo cuando exista; tiene prioridad sobre el borrador.

Cada caso:

```json
{
  "id": "text-01",
  "question": "¿En qué lenguaje está desarrollada la aplicación?",
  "expected_pages": [3],
  "needs_figure": false,
  "should_refuse": false,
  "split": "calibration",
  "notes": "La página 3 indica Node.js."
}
```

`expected_pages` es 1-based. En rechazos va vacío y `should_refuse=true`.
Por defecto el reporte usa solo `split=test`; `--all` usa todos los casos.

## Ejecución

```bash
make eval-baseline          # eval/results/baseline-v2.json
make eval LABEL=after       # eval/results/after.json
make eval-compare LABEL=after
```

Variables: `DEMO_PDF` (admite espacios), `API_URL` (default
`http://localhost:8000`; se detecta `API_PREFIX`/`/v1`), `LABEL` y `RUNS`
(default 3). El script sube el PDF si hace falta (`--ensure-doc`) y espera al job
`COMPLETED`.

Cada corrida envía `temperature=0` por request. `--runs N` repite el dataset y
el reporte usa la mediana de las métricas; el JSON conserva cada corrida.

## Métricas

| Dimensión | Métrica |
| --- | --- |
| Recuperación | `retrieval_hit`: página esperada entre los `retrieved[]` con `sent=true` |
| Respuesta | `answer_hit`: página esperada entre las fuentes citadas |
| Contexto visual | `figure_hit`: respuesta con imagen para casos `needs_figure` |
| Defensividad | `refusal_correct`: `should_refuse` coincide con `sufficient=false` |
| Tokens | media/p95 de `contextTokens`, `promptTokens` y `chunksSent`; desglose system/history/context/question/template |
| Uso del LLM | tasa de `llmCalled` |
| Separación | p50/p95 de `denseCosine` en contestables vs rechazos |
| Latencia | p50 y p95 de `usage.latencyMs` |

## Desglose de tokens

`systemTokens`, `historyTokens`, `contextTokens`, `questionTokens` y
`promptTemplateTokens` se estiman con `count_tokens` (palabras + signos) sobre
las piezas exactas del prompt. `promptEstimatedTokens` es la suma de esas piezas
(con separadores) y `promptTokens` es el total real del proveedor cuando existe.
`promptSource`/`completionSource` etiquetan cada cifra como `provider` o
`estimated`; la diferencia entre ambos mundos es el tokenizador del proveedor.
