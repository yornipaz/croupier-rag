#!/usr/bin/env bash
# Ensambla la demo final: tarjetas, video, audio y subtítulos.
set -euo pipefail

DEMO_DIR="${DEMO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
OUT_DIR="${DEMO_DIR}/out"
PLAN="${OUT_DIR}/plan.json"
SRT="${OUT_DIR}/subtitles.srt"
APP_WEBM="${OUT_DIR}/video/app.webm"
FINAL="${OUT_DIR}/demo.mp4"
CARDS_DIR="${OUT_DIR}/cards"
PADDED_DIR="${OUT_DIR}/audio_padded"

FFMPEG="${FFMPEG:-ffmpeg}"
FFPROBE="${FFPROBE:-ffprobe}"

FONT_BOLD="${DEMO_FONT_BOLD:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}"
FONT_REGULAR="${DEMO_FONT_REGULAR:-/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf}"
BG="0x0b1a14"
GOLD="0xd2ab63"
INK="0xf1eadc"
MUTED="0xa7b4aa"

log() { printf '[build] %s\n' "$*"; }
fail() {
  printf '\n[build] ERROR: %s\n\n' "$*" >&2
  exit 1
}

command -v "$FFMPEG" >/dev/null 2>&1 || fail "No encuentro ffmpeg. Instálalo con: sudo apt install ffmpeg"
command -v "$FFPROBE" >/dev/null 2>&1 || fail "No encuentro ffprobe. Instálalo con: sudo apt install ffmpeg"
[[ -f "$FONT_BOLD" ]] || fail "No encuentro la fuente $FONT_BOLD. Define DEMO_FONT_BOLD."
[[ -f "$FONT_REGULAR" ]] || fail "No encuentro la fuente $FONT_REGULAR. Define DEMO_FONT_REGULAR."
[[ -f "$APP_WEBM" ]] || fail "No existe $APP_WEBM. Ejecuta antes: make demo-record"
[[ -f "$PLAN" ]] || fail "No existe $PLAN. Ejecuta antes: make demo-tts && make demo-record"

log "planificando duraciones y subtítulos…"
python3 "${DEMO_DIR}/make_plan.py"

mkdir -p "$CARDS_DIR" "$PADDED_DIR"
rm -f "$PADDED_DIR"/*.m4a "$OUT_DIR/audio.m4a" "$OUT_DIR/video_noaudio.mp4"

# ---------------------------------------------------------------------------
# 1. Tarjetas de título y cierre (fondo sólido + tipografía, generadas con ffmpeg)
# ---------------------------------------------------------------------------
intro_duration="$(python3 - "$PLAN" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
print(next(seg["duration"] for seg in plan["segments"] if seg["id"] == "intro"))
PY
)"
outro_duration="$(python3 - "$PLAN" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
print(next(seg["duration"] for seg in plan["segments"] if seg["id"] == "outro"))
PY
)"

log "generando tarjeta de título (${intro_duration}s)…"
"$FFMPEG" -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=${BG}:s=1920x1080:r=30:d=${intro_duration}" \
  -vf "drawbox=x=0:y=0:w=1920:h=1080:color=${BG}:t=fill,\
drawbox=x=360:y=300:w=1200:h=2:color=${GOLD}@0.85:t=fill,\
drawtext=fontfile=${FONT_BOLD}:text='C R O U P I E R':fontcolor=${GOLD}:fontsize=34:x=(w-text_w)/2:y=238,\
drawtext=fontfile=${FONT_BOLD}:text='Respuestas con las cartas':fontcolor=${INK}:fontsize=84:x=(w-text_w)/2:y=392,\
drawtext=fontfile=${FONT_BOLD}:text='sobre la mesa':fontcolor=${INK}:fontsize=84:x=(w-text_w)/2:y=492,\
drawtext=fontfile=${FONT_REGULAR}:text='Demo técnica · RAG multimodal para manuales PDF':fontcolor=${MUTED}:fontsize=27:x=(w-text_w)/2:y=650,\
drawtext=fontfile=${FONT_BOLD}:text='Yorni Felipe Bonilla Paz':fontcolor=${INK}:fontsize=34:x=(w-text_w)/2:y=735" \
  -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 \
  -t "$intro_duration" "${CARDS_DIR}/intro.mp4"

log "generando tarjeta de cierre (${outro_duration}s)…"
"$FFMPEG" -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=${BG}:s=1920x1080:r=30:d=${outro_duration}" \
  -vf "drawbox=x=0:y=0:w=1920:h=1080:color=${BG}:t=fill,\
drawbox=x=360:y=330:w=1200:h=2:color=${GOLD}@0.85:t=fill,\
drawtext=fontfile=${FONT_BOLD}:text='Croupier':fontcolor=${GOLD}:fontsize=92:x=(w-text_w)/2:y=380,\
drawtext=fontfile=${FONT_BOLD}:text='Respuestas con las cartas sobre la mesa':fontcolor=${INK}:fontsize=44:x=(w-text_w)/2:y=520,\
drawtext=fontfile=${FONT_REGULAR}:text='Gracias por acompañarme en la mesa':fontcolor=${MUTED}:fontsize=30:x=(w-text_w)/2:y=620,\
drawtext=fontfile=${FONT_BOLD}:text='Yorni Felipe Bonilla Paz':fontcolor=${INK}:fontsize=34:x=(w-text_w)/2:y=720" \
  -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 \
  -t "$outro_duration" "${CARDS_DIR}/outro.mp4"

# ---------------------------------------------------------------------------
# 2. Video de la app recortado a la ventana grabada
# ---------------------------------------------------------------------------
content_start="$(python3 - "$PLAN" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["video"]["contentStart"])
PY
)"
content_duration="$(python3 - "$PLAN" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["video"]["contentDuration"])
PY
)"
source_duration="$("$FFPROBE" -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$APP_WEBM" | head -1)"
pad_needed="$(python3 - "$source_duration" "$content_start" "$content_duration" <<'PY'
import sys
source, start, duration = map(float, sys.argv[1:4])
print(f"{max(0.0, start + duration - source + 0.35):.3f}")
PY
)"

log "recortando video de la app (inicio ${content_start}s, duración ${content_duration}s)…"
app_filter="scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=${BG},fps=30,format=yuv420p"
if python3 -c "import sys; sys.exit(0 if float('${pad_needed}') > 0.01 else 1)"; then
  app_filter="${app_filter},tpad=stop_mode=clone:stop_duration=${pad_needed}"
fi
"$FFMPEG" -y -hide_banner -loglevel error \
  -i "$APP_WEBM" -ss "$content_start" -t "$content_duration" \
  -vf "$app_filter" -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 \
  "${CARDS_DIR}/app.mp4"

# ---------------------------------------------------------------------------
# 3. Pista de audio: un bloque por segmento, rellenado a la duración exacta
# ---------------------------------------------------------------------------
log "preparando audio por segmento…"
python3 - "$PLAN" > "${OUT_DIR}/audio_plan.tsv" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
for seg in plan["segments"]:
    print(f"{seg['index']:04d}\t{seg['id']}\t{seg['audio']}\t{seg['duration']}")
PY

while IFS=$'\t' read -r index segment_id audio duration; do
  [[ -n "${index:-}" ]] || continue
  padded="${PADDED_DIR}/${index}-${segment_id}.m4a"
  "$FFMPEG" -y -hide_banner -loglevel error -i "$audio" \
    -af "apad=whole_dur=${duration},atrim=0:${duration},aresample=48000" \
    -ac 2 -ar 48000 -c:a aac -b:a 192k "$padded"
done < "${OUT_DIR}/audio_plan.tsv"

: > "${OUT_DIR}/audio_list.txt"
while IFS= read -r padded; do
  printf "file '%s'\n" "$padded" >> "${OUT_DIR}/audio_list.txt"
done < <(find "$PADDED_DIR" -maxdepth 1 -name '*.m4a' -print | sort)

"$FFMPEG" -y -hide_banner -loglevel error \
  -f concat -safe 0 -i "${OUT_DIR}/audio_list.txt" \
  -c:a aac -b:a 192k -ar 48000 -ac 2 "${OUT_DIR}/audio.m4a"

# ---------------------------------------------------------------------------
# 4. Concatenar tarjetas + app y mezclar audio/subtítulos
# ---------------------------------------------------------------------------
log "concatenando video…"
cat > "${OUT_DIR}/video_list.txt" <<EOF
file '${CARDS_DIR}/intro.mp4'
file '${CARDS_DIR}/app.mp4'
file '${CARDS_DIR}/outro.mp4'
EOF

"$FFMPEG" -y -hide_banner -loglevel error \
  -f concat -safe 0 -i "${OUT_DIR}/video_list.txt" \
  -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 \
  "${OUT_DIR}/video_noaudio.mp4"

log "mezclando audio y subtítulos…"
"$FFMPEG" -y -hide_banner -loglevel error \
  -i "${OUT_DIR}/video_noaudio.mp4" \
  -i "${OUT_DIR}/audio.m4a" \
  -i "$SRT" \
  -map 0:v:0 -map 1:a:0 -map 2:s:0 \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -ac 2 -c:s mov_text \
  -metadata:s:a:0 language=spa -metadata:s:a:0 title="Narración" \
  -metadata:s:s:0 language=spa -metadata:s:s:0 title="Español" \
  -metadata title="Croupier · Respuestas con las cartas sobre la mesa" \
  -metadata artist="Yorni Felipe Bonilla Paz" \
  -movflags +faststart -shortest "$FINAL"

# ---------------------------------------------------------------------------
# 5. Verificación y resumen
# ---------------------------------------------------------------------------
python3 - "$FINAL" "$PLAN" "$FFPROBE" <<'PY'
import json
import subprocess
import sys

final, plan_path, ffprobe = sys.argv[1:4]
plan = json.load(open(plan_path, encoding="utf-8"))
probe = json.loads(
    subprocess.check_output(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of", "json", final,
        ],
        text=True,
    )
)
streams = probe.get("streams", [])
video = next((s for s in streams if s.get("codec_type") == "video"), {})
audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
subs = next((s for s in streams if s.get("codec_type") == "subtitle"), {})
duration = float(probe["format"]["duration"])
size_mb = float(probe["format"]["size"]) / (1024 * 1024)

problems = []
if video.get("codec_name") != "h264":
    problems.append(f"video={video.get('codec_name')} (se esperaba h264)")
if audio.get("codec_name") != "aac":
    problems.append(f"audio={audio.get('codec_name')} (se esperaba aac)")
if not subs:
    problems.append("falta la pista de subtítulos")
if video.get("width") != 1920 or video.get("height") != 1080:
    problems.append(f"resolución={video.get('width')}x{video.get('height')} (se esperaba 1920x1080)")
if video.get("r_frame_rate") not in {"30/1", "30000/1001"}:
    problems.append(f"fps={video.get('r_frame_rate')} (se esperaba 30/1)")
if not (180.0 <= duration <= 270.0):
    problems.append(f"duración={duration:.1f}s (se esperaba entre 180 y 270s)")
if abs(duration - float(plan["totalDuration"])) > 0.5:
    problems.append(
        f"la duración final ({duration:.2f}s) no coincide con el plan ({plan['totalDuration']:.2f}s)"
    )
if problems:
    print("\n[build] ERROR: la verificación falló:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    sys.exit(1)

def hms(value: float) -> str:
    value = int(round(value))
    return f"{value // 3600:02d}:{(value % 3600) // 60:02d}:{value % 60:02d}"

print()
print("=" * 78)
print("CROUPIER · DEMO GENERADA")
print("=" * 78)
print(f"Duración total : {hms(duration)} ({duration:.1f}s)")
print(f"Video          : {video.get('codec_name')} {video.get('width')}x{video.get('height')} @ {video.get('r_frame_rate')} fps")
print(f"Audio          : {audio.get('codec_name')} 48 kHz estéreo")
print(f"Subtítulos     : {subs.get('codec_name', 'mov_text')} (español) + SRT externo")
print(f"Archivo        : {final}")
print(f"Tamaño         : {size_mb:.1f} MB")
print("-" * 78)
print("Duración por segmento:")
for segment in plan["segments"]:
    print(
        f"  {segment['index']:>2}. {segment['id']:<18} "
        f"{segment['start']:7.2f}s → +{segment['duration']:6.2f}s  "
        f"({segment['kind']})"
    )
print("=" * 78)
PY

# Fotogramas negros: umbral bajo para no confundir el tema oscuro con un fallo.
log "comprobando fotogramas negros…"
black_log="$(mktemp)"
if ! "$FFMPEG" -hide_banner -i "$FINAL" -vf "blackdetect=d=0.15:pix_th=0.02" -an -f null - 2>"$black_log"; then
  rm -f "$black_log"
  fail "ffmpeg falló durante la comprobación de fotogramas negros."
fi
if grep -q "black_start" "$black_log"; then
  grep "black_start" "$black_log" | head -5 >&2
  rm -f "$black_log"
  fail "Se detectaron fotogramas negros en la demo."
fi
rm -f "$black_log"

log "listo: ${FINAL}"
