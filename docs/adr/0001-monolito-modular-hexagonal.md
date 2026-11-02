# ADR 0001 — Monolito modular con arquitectura hexagonal por módulo

- **Estado:** aceptado
- **Fecha:** 2026-11-01

## Contexto

El sistema debe ingerir PDFs técnicos, indexarlos y responder preguntas mostrando la fuente y el
diagrama relevante. Es una prueba técnica donde se evalúan arquitectura limpia, asincronía,
resiliencia e integración de IA. Necesitamos límites claros sin pagar el coste operativo de
microservicios.

## Decisión

Un único despliegue (monolito modular) con siete módulos de negocio y arquitectura hexagonal dentro
de cada módulo:

```text
app/modules/<module>/
├── domain/          # Entidades y reglas puras (stdlib + pydantic opcional)
├── application/     # Puertos (Protocol), casos de uso y DTOs
├── infrastructure/  # Adapters: Qdrant, Redis, PyMuPDF, Gemini, Ollama, fastembed
├── presentation/    # Routers y schemas HTTP
└── module.py        # Composition root del módulo (router + factories)
```

Módulos: `documents`, `ingestion`, `ai`, `vector_store`, `retrieval`, `chat`, `health`.

Reglas de dependencia:

1. `domain` no importa frameworks ni SDKs externos.
2. Los casos de uso dependen solo de puertos, nunca de adapters.
3. Un módulo solo importa puertos/DTOs públicos de otro; jamás sus adapters.
4. El proveedor concreto se elige en `module.py` según configuración.
5. La inyección HTTP pasa por `Depends`; los tests usan `dependency_overrides`.

`apps/api/.importlinter` valida las reglas 1–3 en CI (`make lint-arch`).

## Consecuencias

- Un solo proceso API + un worker Celery comparten código y contratos.
- Los límites se pueden verificar automáticamente y extraer a servicios si hiciera falta.
- El composition root (`app/bootstrap.py` + `module.py`) es el único lugar que conoce adapters.
- La disciplina de puertos añade algo de código, pero mantiene los casos de uso testeables sin red.
