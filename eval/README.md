# Evaluación

Carpeta reservada para el conjunto de evaluación del RAG. Todavía no contiene casos: el pipeline de
ingesta y chat se implementa en fases posteriores.

## Qué mediremos

| Dimensión | Métrica | Cómo |
| --- | --- | --- |
| Recuperación | Hit@k y MRR | Preguntas con `doc_id` + página esperada. |
| Grounding | Citas correctas / respuestas | Cada `[S1]` debe existir en las fuentes y sustentar la afirmación. |
| Defensividad | Falsos positivos | Preguntas fuera del corpus deben responder "No tengo información suficiente". |
| Contexto visual | Imagen relevante | La imagen devuelta debe corresponder a la figura citada. |
| Resiliencia | Comportamiento ante 429/5xx/timeout | Retry acotado y breaker abierto sin filtrar trazas. |
| Latencia | p50 / p95 | Ingesta por página y `POST /chat/ask`. |

## Formato propuesto de caso

```json
{
  "id": "pump-001",
  "question": "¿Qué presión máxima admite la bomba?",
  "expected": {
    "document": "manual-bomba.pdf",
    "page": 42,
    "answerContains": ["10 bar"],
    "imageId": "fig-3"
  }
}
```

Los casos reales se añadirán junto con los PDFs de ejemplo en la fase de evaluación.
