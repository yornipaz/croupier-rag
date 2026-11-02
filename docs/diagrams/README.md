# Diagramas interactivos

Cuatro artefactos HTML autocontenidos, generados con [Archify](https://github.com/tt-a1i/archify)
en perfil `showcase`. Se abren directamente en el navegador; no necesitan el stack de Croupier.

| Diagrama | Artefacto | Spec | SHA-256 |
| --- | --- | --- | --- |
| Arquitectura | [architecture.html](architecture.html) | [architecture.json](src/architecture.json) | `c27e17bf653931fbcaf3dd0e6c001364dc7a7e3d66faf94e8c6e26384f086299` |
| Ingesta | [ingestion-workflow.html](ingestion-workflow.html) | [ingestion-workflow.json](src/ingestion-workflow.json) | `144f8c811b9a0f4295ad227d7b081b4ab32eb3d2dde2d53a4a6948b5054ee4b9` |
| Consulta | [chat-sequence.html](chat-sequence.html) | [chat-sequence.json](src/chat-sequence.json) | `1c99bcaae2a41a26b5230d01c27dedc25ba0506ba62d4570c6ec659f33fdfc8d` |
| Ciclo de vida | [job-lifecycle.html](job-lifecycle.html) | [job-lifecycle.json](src/job-lifecycle.json) | `b3cf1bf142d48f3f6053c19db156d2dcf4b9de690962f47061ed5bc09ef3ec8c` |

## Verificación

Cada artefacto pasó:

- validación de esquema;
- 9 checks de artefacto;
- composición `showcase`: 0 errores, 0 warnings;
- `visual-check` automatizado en 1440×900, 1600×1000, 1920×1080 y 2048×1320, en claro y oscuro,
  sin overflow y con legibilidad mínima;
- revisión visual perceptual sobre las capturas generadas.

Los receipts, contact sheets y capturas `*.visual-check.*` se generan localmente y están ignorados
por Git para no inflar el repositorio. El HTML entregado es el artefacto versionado.

## Regenerar

```bash
ARCHIFY=~/.agents/skills/archify/bin/archify.mjs

node "$ARCHIFY" validate architecture docs/diagrams/src/architecture.json --quality showcase
node "$ARCHIFY" deliver architecture docs/diagrams/src/architecture.json docs/diagrams/architecture.html --quality showcase

node "$ARCHIFY" validate workflow docs/diagrams/src/ingestion-workflow.json --quality showcase
node "$ARCHIFY" deliver workflow docs/diagrams/src/ingestion-workflow.json docs/diagrams/ingestion-workflow.html --quality showcase

node "$ARCHIFY" validate sequence docs/diagrams/src/chat-sequence.json --quality showcase
node "$ARCHIFY" deliver sequence docs/diagrams/src/chat-sequence.json docs/diagrams/chat-sequence.html --quality showcase

node "$ARCHIFY" validate lifecycle docs/diagrams/src/job-lifecycle.json --quality showcase
node "$ARCHIFY" deliver lifecycle docs/diagrams/src/job-lifecycle.json docs/diagrams/job-lifecycle.html --quality showcase
```

Para recoger evidencia de navegador:

```bash
node "$ARCHIFY" visual-check docs/diagrams/architecture.html --json
```

## Lectura recomendada

1. [Arquitectura](architecture.html): contenedores, límites y dependencias.
2. [Ingesta](ingestion-workflow.html): qué ocurre desde el PDF hasta Qdrant.
3. [Consulta](chat-sequence.html): retrieval, guard defensivo, DeepSeek y validación.
4. [Ciclo de vida](job-lifecycle.html): estados, retry y salidas terminales.
