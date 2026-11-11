# Evaluación

Harness reproducible para comparar versiones del RAG sobre un manual técnico.

## Dataset

- `golden.json`: dataset integrado y versionado (24 preguntas, 8 rechazos, split 50/50).
- `golden.draft.json`: borrador original de 12 preguntas.
- `golden.extra.draft.json`: 10 preguntas revisadas e integradas en `golden.json`.
- `golden.refusal.draft.json`: 2 rechazos adicionales para alcanzar 8 y el mínimo de 24
  (integrados en `golden.json`, pendientes de revisión final).

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
make eval-baseline          # eval/results/baseline-v3.json
make eval LABEL=static      # selección previa + contexto compacto
make eval LABEL=dynamic     # gate + cutoff + MMR
make eval-compare LABEL=dynamic
make calibrate              # DATA_DIR/calibration.json
make reindex                # obligatorio tras cambiar parser/chunking
```

Variables: `DEMO_PDF` (admite espacios), `API_URL` (default
`http://localhost:8000`; se detecta `API_PREFIX`/`/v1`), `LABEL` y `RUNS`
(default 3). El script sube el PDF si hace falta (`--ensure-doc`) y espera al job
`COMPLETED`.

Cada corrida envía `temperature=0` por request. `--runs N` repite el dataset y
el reporte usa la mediana de las métricas; el JSON conserva cada corrida.
`LABEL=dynamic` envía `X-Selection-Mode: dynamic` (solo el API con `ENV=dev|eval`
lo acepta); el resto usa `static`.

Cada JSON de `eval/results/` incluye `schemaVersion`, `label`, `createdAt`,
`gitCommit`, `split`, `datasetHash`, `nQuestions`, `nRuns`, `selectionMode` y la
configuración de evaluación relevante. `make eval-compare` falla sin imprimir la
tabla si difieren `schemaVersion`, `datasetHash`, `split` o `nQuestions`; los
campos ausentes en resultados antiguos se avisan y se muestran como `n/d`.

## Diagnósticos

```bash
python eval/analyze_signals.py        # señales del split calibration, sin LLM
python eval/diagnose_section_paths.py # longitudes y section_path sospechosos
```

`analyze_signals.py` usa `POST /retrieval/search?debug=true` y agrupa
contestables/rechazos. Para cada pregunta muestra `denseCosine` top1,
separación top1-mediana del pool, `lexicalCoverage` y `sparseScore` top1. También
busca umbrales con cero falsos rechazos en contestables.

`diagnose_section_paths.py` lee los payloads de Qdrant y reporta la distribución
de longitud de `section_path`, los 10 más largos y los bloques del PDF que
apuntan a posibles encabezados detectados por error.

`calibrate.py` usa solo el split `calibration`, calcula el par de señales y los
umbrales con `GATE_SAFETY_MARGIN`, calibra `REL_RATIO`/`GAP_RATIO` conservando las
páginas esperadas y escribe `DATA_DIR/calibration.json`. `make calibrate` lo copia
al contenedor `api`. Si el fichero falta o no coincide con `EMBEDDING_MODEL`, el
gate queda desactivado y todo pasa al LLM.

## Selección dinámica

- `CANDIDATE_POOL=20` candidatos híbridos RRF.
- `RelevanceGate` conservador: dos señales, `REJECT|ACCEPT|UNSURE`; solo `REJECT`
  evita el LLM y exige que **ambas** señales estén por debajo del umbral calibrado.
- `AdaptiveCutoff`: `REL_RATIO`, `GAP_RATIO`, `MIN_K`, `MAX_K`.
- `ContextPacker`: MMR (`MMR_LAMBDA`) con vectores densos, deduplicación
  (`MMR_DUPLICATE_THRESHOLD`) y presupuesto `CONTEXT_TOKEN_BUDGET` corregido por
  `TOKEN_ESTIMATE_FACTOR`.

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
