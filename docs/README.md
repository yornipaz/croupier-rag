# Documentación

| Documento | Contenido |
| --- | --- |
| [Arquitectura](architecture.md) | Contexto, contenedores, módulos, contratos, flujos, proveedores, operación y troubleshooting |
| [Diagramas interactivos](diagrams/README.md) | HTML navegables y specs Archify de arquitectura, ingesta, consulta y ciclo de vida |
| [ADR 0001](adr/0001-monolito-modular-hexagonal.md) | Monolito modular con puertos y adapters |
| [ADR 0002](adr/0002-rrf-fastembed-bm25.md) | Qdrant híbrido, RRF y FastEmbed/BM25 |

## Recorrido rápido

1. `architecture.md` explica el sistema completo y enlaza los diagramas.
2. `diagrams/architecture.html` da la vista de contenedores.
3. `diagrams/ingestion-workflow.html` sigue un PDF hasta Qdrant.
4. `diagrams/chat-sequence.html` sigue una pregunta hasta la respuesta con fuentes.
5. `diagrams/job-lifecycle.html` muestra estados, retry y fallos.

Los diagramas son autocontenidos: se pueden abrir sin levantar la API, la web o Docker.
