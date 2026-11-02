ROL: Eres un ingeniero de software que automatiza demos en video de aplicaciones web.

CONTEXTO DEL PROYECTO
Proyecto: "Croupier", un sistema RAG multimodal para manuales técnicos en PDF. Eslogan: "Respuestas con las cartas sobre la mesa".

- Backend FastAPI en http://localhost:8000; frontend Angular en http://localhost:4200.
- Flujos de UI a mostrar: (1) subir un PDF y ver la línea de tiempo de ingesta (parsing, imágenes, chunking, embeddings, indexando) hasta COMPLETED;
  (2) hacer una pregunta cuya respuesta depende de una figura y mostrar fuente (archivo y página) + imagen asociada;
  (3) abrir "Ver en la página" y mostrar el modal con el fragmento resaltado;
  (4) hacer una pregunta sin respuesta en el documento y mostrar el estado "sin información suficiente";
  (5) activar "Modo auditor" y mostrar los chunks recuperados con score y rank denso/sparse.
- PDF de demo: "/home/yfbp/Downloads/Manual de usuario app.pdf" (pásalo como variable de entorno DEMO_PDF; no lo copies dentro del repositorio).
  Pregunta de calentamiento: "¿Qué hace la aplicación y dónde almacena los pedidos que descarga?".
  Pregunta con figura: "[ELIGE UNA DE LAS TRES SEGÚN LAS FIGURAS DEL PDF]".
  Pregunta sin respuesta: "¿Cómo se integra la aplicación con los pedidos de Mercadona?".
- Orden en el video: calentamiento (texto con fuente) → pregunta con figura → página resaltada → pregunta sin respuesta → modo auditor.

OBJETIVO
Generar automáticamente un video de 3 a 4 minutos, 1080p, 30 fps, MP4 (H.264 + AAC), con narración en español, subtítulos y cursor visible.
Debe poder regenerarse con un solo comando: `make demo`.

ENTREGABLES (carpeta demo/)

1. demo/script.yaml: lista ordenada de segmentos {id, narration, action, audio_file?}. Acciones: intro, architecture, upload, ask_figure,
   show_page, ask_unknown, auditor_mode, outro. `audio_file` opcional para reemplazar la voz sintética por una grabación mía.
2. demo/tts.py: genera un MP3 por segmento con edge-tts (voz es-CO-GonzaloNeural, configurable) y mide su duración con ffprobe en demo/out/durations.json.
3. demo/record.ts (Playwright, Chromium): usa recordVideo en 1920x1080, mueve el mouse con trayectorias suaves, dibuja un cursor visible y un
   efecto de clic inyectando CSS/JS, escribe las preguntas carácter a carácter (~45 ms), y espera por selectores (no por sleeps fijos).
   Cada segmento dura como mínimo la duración de su audio + 0.6 s. Usa data-testid para los selectores; si faltan en el frontend,
   añádelos SIN tocar la lógica (lista los que agregaste).
4. demo/build.sh: ffmpeg para concatenar audios con los mismos tiempos, generar subtítulos SRT desde script.yaml y unir todo en demo/out/demo.mp4
   (yuv420p, CRF 18). Tarjetas de título y cierre generadas con ffmpeg (fondo sólido, "Croupier", el eslogan y mi nombre: Yorni Felipe Bonilla Paz).
5. Makefile: `make demo` (todo), `make demo-dry` (recorre el flujo sin grabar, para validar selectores) y `make demo-clean`.
6. demo/README.md: requisitos (Node, Python, ffmpeg), cómo instalar (npm i -D @playwright/test; npx playwright install chromium; pip install edge-tts) y cómo correr.

GUION (tú lo redactas en script.yaml)

- Español natural, en primera persona, tono cercano y profesional, sin tecnicismos sin explicar. Máximo 35 palabras por segmento.
- Estructura: intro (qué problema resuelve Croupier) → arquitectura en una frase (módulos, cola asíncrona, búsqueda híbrida) → ingesta en vivo →
  pregunta con figura → página resaltada → pregunta sin respuesta (defensa contra alucinaciones: "aquí no apuesto") → modo auditor ("el Pit Boss")
  → cierre (tests, evaluación, escalabilidad).
- Menciona qué se está viendo en pantalla en el momento justo en que ocurre.

REGLAS

- Determinismo: si el servicio no responde, falla con un mensaje claro indicando qué levantar (docker compose up). Reintenta un segmento fallido 2 veces.
- No cambies la lógica de la aplicación. No incluyas datos sensibles ni llaves de API en el video ni en logs.
- Si no puedes ejecutar comandos, entrégame cada archivo completo en bloques de código con su ruta exacta y los comandos para correrlo.

CRITERIOS DE ACEPTACIÓN

- `make demo-dry` pasa sin errores; `make demo` produce demo/out/demo.mp4 de entre 3:00 y 4:30, sin fotogramas negros, audio sincronizado y subtítulos legibles.
- Al terminar, imprime un resumen: duración total, duración por segmento y la ruta del archivo.
