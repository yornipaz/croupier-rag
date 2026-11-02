# Demo en video de Croupier

Genera automáticamente `demo/out/demo.mp4` (1920×1080, 30 fps, H.264 + AAC) con
narración en español, subtítulos, cursor visible y los cinco flujos de la
aplicación:

1. subida del PDF y línea de tiempo de ingesta hasta `COMPLETED`;
2. pregunta de calentamiento con respuesta y fuente;
3. pregunta cuya respuesta se apoya en una figura del manual;
4. modal «Ver en la página» con el fragmento resaltado;
5. pregunta sin respaldo documental y modo auditor con scores y rankings.

## Requisitos

| Herramienta | Versión / notas |
| --- | --- |
| Node.js | 22.6+ (recomendado 24). Ejecuta TypeScript sin compilar con `--experimental-strip-types`. |
| Python | 3.10+ con `edge-tts` y `PyYAML`. |
| ffmpeg / ffprobe | Cualquier build reciente con `libx264`, `aac`, `drawtext` y `mov_text`. |
| Docker | Stack de Croupier levantado: `api`, `worker`, `redis`, `qdrant` y `web`. |
| Chromium | Instalado por Playwright (`npx playwright install chromium`). |

El frontend debe ser el build de producción servido por Docker
(`http://localhost:4200`). Con `ng serve` el proyecto usa `environment.useMock = true`
y la demo fallaría a propósito con el mensaje «modo mock».

## Instalación

Desde la raíz del repositorio:

```bash
# 1. Dependencias de Python (si tu entorno lo permite)
python3 -m pip install --user edge-tts pyyaml

# 2. Dependencias de Node y Chromium
make demo-deps
# equivale a:
#   cd demo && npm install
#   cd demo && npx playwright install chromium

# 3. Stack de Croupier
docker compose up -d --build
docker compose ps
```

Si `pip install --user` está bloqueado por PEP 668, crea un entorno virtual y
ejecuta `make demo` con ese Python:

```bash
python3 -m venv .venv-demo
. .venv-demo/bin/activate
pip install edge-tts pyyaml
make demo PYTHON=python
```

## Uso

```bash
# Demo completa (voz + grabación + montaje)
DEMO_PDF="$HOME/Downloads/Manual de usuario app.pdf" make demo

# Solo validar selectores y recorrer el flujo, sin grabar
DEMO_PDF="$HOME/Downloads/Manual de usuario app.pdf" make demo-dry

# Borrar artefactos generados
make demo-clean
```

`DEMO_PDF` tiene un valor por defecto:
`$HOME/Downloads/Manual de usuario app.pdf`. Puedes sobreescribirlo:

```bash
make demo DEMO_PDF="/ruta/a/otro/manual.pdf"
```

Al terminar, `make demo` imprime la duración total, la duración de cada
segmento y la ruta del MP4.

## Variables de entorno

| Variable | Por defecto | Uso |
| --- | --- | --- |
| `DEMO_PDF` | `$HOME/Downloads/Manual de usuario app.pdf` | PDF que se sube en la demo. |
| `APP_URL` | `http://localhost:4200` | Frontend servido por Docker. |
| `API_URL` | autodetectado | API directa; por defecto prueba `http://localhost:8000/v1`. |
| `TTS_VOICE` | `es-CO-GonzaloNeural` | Voz de edge-tts. |
| `TTS_RATE` | `+0%` | Velocidad de la voz, por ejemplo `-8%`. |
| `FFMPEG` / `FFPROBE` | `ffmpeg` / `ffprobe` | Binarios a usar. |
| `HEADLESS` | `true` | `false` abre Chromium para depurar. |
| `DEMO_FONT_BOLD` / `DEMO_FONT_REGULAR` | DejaVu Sans | Fuentes de las tarjetas. |

## Guion

`demo/script.yaml` es la fuente de verdad. Cada segmento tiene:

```yaml
- id: figure
  action: ask_figure
  question: ¿Qué indica el número entre corchetes?
  narration: Ahora la pregunta con figura…
```

- `id`: identificador único.
- `action`: `intro`, `architecture`, `upload`, `ask_figure`, `show_page`,
  `ask_unknown`, `auditor_mode` u `outro`.
- `narration`: máximo 35 palabras; `tts.py` falla si se supera.
- `audio_file` (opcional): ruta relativa a `demo/` con una grabación propia.
  Si existe, no se sintetiza voz para ese segmento.
- `question` (opcional): texto que se escribe en el chat en los segmentos
  `ask_figure`, `ask_unknown` y `auditor_mode`.

Preguntas usadas:

- Calentamiento: «¿Qué hace la aplicación y dónde almacena los pedidos que
  descarga?».
- Figura: «Según la captura de la app móvil, ¿qué indica el número entre
  corchetes junto a cada tienda y de qué color se muestra una tienda sin
  pedidos pendientes?». La respuesta se apoya en la captura de la página 20
  del manual y devuelve la imagen enlazada.
- Sin respuesta: «¿Cómo se integra la aplicación con los pedidos de Mercadona?».

Para usar tu propia voz, deja el MP3 en `demo/audio/` y añade `audio_file`:

```yaml
- id: intro
  action: intro
  audio_file: audio/intro-yorni.mp3
  narration: Esto es Croupier…
```

`tts.py` mide el archivo con `ffprobe` y `build.sh` lo usa sin volver a
sintetizarlo.

## Cómo funciona

1. **`demo/tts.py`**
   - Lee `script.yaml`, valida las 35 palabras y genera un MP3 por segmento con
     edge-tts (`es-CO-GonzaloNeural` por defecto).
   - Mide cada audio con `ffprobe` y escribe `demo/out/durations.json` y
     `demo/out/script.json`.
   - Cachea la voz por hash de texto+voz+rate para acelerar regeneraciones.

2. **`demo/record.ts`** (Playwright + Chromium)
   - Abre un contexto con `recordVideo` a 1920×1080 y 30 fps.
   - Inyecta un cursor SVG y un anillo de clic en todas las páginas, y oculta
     el cursor nativo.
   - Mueve el ratón con trayectorias suaves y escribe a 45 ms por carácter.
   - Espera por `data-testid` y por atributos de estado (`data-job-status`,
     `data-stage-state`, etc.), nunca por sleeps fijos para sincronizar.
   - Cada segmento se rellena hasta `audio + 0.6 s` como mínimo.
   - Reintenta un segmento fallido hasta 3 intentos (2 reintentos), recargando
     la vista y conservando el documento seleccionado.
   - Borra antes el documento de demo con el mismo nombre para que la subida
     sea real y reproducible.
   - Guarda `demo/out/timeline.json` con los tiempos reales de cada segmento y
     calibra el inicio del WebM con `ffprobe`.

3. **`demo/make_plan.py`**
   - Cruza `script.json` y `timeline.json`, valida que cada segmento cumple
     `audio + 0.6 s`, calcula el plan final y genera `demo/out/subtitles.srt`.

4. **`demo/build.sh`**
   - Genera con ffmpeg las tarjetas de título y cierre (fondo sólido, Croupier,
     el eslogan y «Yorni Felipe Bonilla Paz»).
   - Recorta el WebM a la ventana útil, rellena cada audio a la duración exacta
     del segmento, concatena video y audio, y muxea los subtítulos
     (`mov_text`, español).
   - Verifica H.264, AAC, 1920×1080, 30 fps, subtítulos y duración entre 3:00 y
     4:30; también detecta fotogramas negros.

## Artefactos

```text
demo/out/
├── audio/                # MP3 sintetizados por segmento
├── audio_padded/         # audio rellenado a la duración del segmento
├── cards/                # tarjetas y video de la app normalizados
├── video/app.webm        # grabación original de Playwright
├── durations.json        # duración medida de cada audio
├── script.json           # guion + audio + duraciones
├── timeline.json         # tiempos reales de los segmentos grabados
├── plan.json             # plan temporal final
├── subtitles.srt         # subtítulos externos
└── demo.mp4              # entrega final
```

## `data-testid` añadidos al frontend

Solo se añadieron atributos de test; no se modificó ninguna lógica de la
aplicación.

| Archivo | `data-testid` |
| --- | --- |
| `core/layout/sidebar.html` | `nav-documents`, `new-conversation` |
| `core/layout/header.ts` | `auditor-toggle`, `mock-badge` |
| `features/documents/documents-page.html` | `documents-page` |
| `features/documents/components/documents-panel.html` | `documents-upload`, `documents-file-input`, `documents-select-file`, `active-ingestion`, `document-card` (+ `data-document-id`, `data-filename`), `document-status`, `document-ask` |
| `features/documents/components/job-timeline.html` | `job-timeline` (+ `data-job-status`, `data-job-stage`, `data-job-progress`, `data-job-id`), `job-title`, `job-progress`, `job-stage` (+ `data-stage-key`, `data-stage-state`) |
| `features/chat/chat-page.html` | `chat-page`, `inspector-open` |
| `features/chat/components/chat-composer.html` | `chat-input`, `chat-send`, `chat-document-select` |
| `features/chat/components/chat-message.html` | `user-message`, `assistant-message` (+ `data-sufficient`), `insufficient-answer` |
| `features/chat/components/figure-viewer.html` | `figure-viewer`, `figure-open`, `figure-page-link`, `figure-page-modal`, `figure-page-close`, `figure-page-image` |
| `features/inspector/retrieval-inspector.html` | `retrieval-inspector`, `inspector-close`, `inspector-best-score`, `retrieval-hit` (+ `data-page`, `data-dense-rank`, `data-sparse-rank`) |
| `shared/ui/source-chips.ts` | `source-chip` (+ `data-page`) |

## Solución de problemas

- **«El frontend no responde» / «La API no responde»**: ejecuta
  `docker compose up -d --build` y espera a que `docker compose ps` muestre todo
  sano. Los logs útiles son `docker compose logs -f api worker`.
- **«El frontend está en modo mock»**: estás usando `ng serve`. La demo necesita
  el contenedor `web` con el build de producción.
- **«No encuentro data-testid=…»**: reconstruye el frontend tras actualizar el
  repositorio con `docker compose up -d --build web`.
- **No hay voz**: edge-tts necesita red. Comprueba `python3 -c "import edge_tts"`.
  También puedes usar `audio_file`.
- **El video dura menos de 3:00 o más de 4:30**: `make_plan.py` falla con el
  total calculado. Ajusta la narración (máximo 35 palabras) o añade/elimina
  segmentos de observación en `script.yaml`.
- **ffmpeg no encuentra una fuente**: define `DEMO_FONT_BOLD` y
  `DEMO_FONT_REGULAR` con rutas a `.ttf` que existan.
- **Chromium no está instalado**: `cd demo && npx playwright install chromium`.
