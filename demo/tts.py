#!/usr/bin/env python3
"""Genera la narración de la demo y mide la duración real de cada segmento.

Lee ``demo/script.yaml``, sintetiza un MP3 por segmento con edge-tts (salvo que
el segmento declare ``audio_file``) y escribe:

    demo/out/audio/<id>.mp3
    demo/out/durations.json
    demo/out/script.json

``script.json`` es el contrato que consumen ``record.ts`` y ``build.sh``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEMO_DIR = Path(__file__).resolve().parent
OUT_DIR = DEMO_DIR / "out"
AUDIO_DIR = OUT_DIR / "audio"
DURATIONS_FILE = OUT_DIR / "durations.json"
SCRIPT_FILE = OUT_DIR / "script.json"
CACHE_FILE = OUT_DIR / "tts-cache.json"

DEFAULT_VOICE = "es-CO-GonzaloNeural"
DEFAULT_RATE = "+0%"
MAX_WORDS = 35
SYNTH_RETRIES = 3


@dataclass(frozen=True)
class Segment:
    id: str
    action: str
    narration: str
    question: str | None
    audio_file: str | None


def fail(message: str) -> None:
    print(f"\n[tts] ERROR: {message}\n", file=sys.stderr)
    raise SystemExit(1)


def log(message: str) -> None:
    print(f"[tts] {message}", flush=True)


def load_script() -> list[Segment]:
    script_path = DEMO_DIR / "script.yaml"
    if not script_path.exists():
        fail(f"No existe {script_path}. Ejecuta `make demo` desde la raíz del repositorio.")
    raw = yaml.safe_load(script_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("segments")
    if not isinstance(entries, list) or not entries:
        fail("script.yaml debe contener una lista no vacía en `segments`.")

    allowed = {
        "intro",
        "architecture",
        "upload",
        "ask_figure",
        "show_page",
        "ask_unknown",
        "auditor_mode",
        "outro",
    }
    segments: list[Segment] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            fail(f"El segmento #{index} no es un objeto.")
        missing = [key for key in ("id", "narration", "action") if not entry.get(key)]
        if missing:
            fail(f"El segmento #{index} no tiene: {', '.join(missing)}.")
        segment_id = str(entry["id"]).strip()
        if segment_id in seen:
            fail(f"Id de segmento duplicado: {segment_id}.")
        seen.add(segment_id)
        action = str(entry["action"]).strip()
        if action not in allowed:
            fail(f"Acción desconocida en `{segment_id}`: {action}.")
        narration = " ".join(str(entry["narration"]).split())
        words = count_words(narration)
        if words > MAX_WORDS:
            fail(
                f"`{segment_id}` tiene {words} palabras; el máximo es {MAX_WORDS}. "
                "Acorta la narración para mantener el ritmo del video."
            )
        question = entry.get("question")
        audio_file = entry.get("audio_file")
        segments.append(
            Segment(
                id=segment_id,
                action=action,
                narration=narration,
                question=" ".join(str(question).split()) if question else None,
                audio_file=str(audio_file).strip() if audio_file else None,
            )
        )
    return segments


def count_words(text: str) -> int:
    return len(re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", text))


def resolve_executable(name: str, env_var: str) -> str:
    configured = os.environ.get(env_var)
    if configured:
        return configured
    found = shutil.which(name)
    if found:
        return found
    fail(
        f"No encuentro `{name}`. Instala ffmpeg (incluye {name}) y vuelve a intentarlo.\n"
        "  Ubuntu/Debian: sudo apt install ffmpeg\n"
        "  macOS: brew install ffmpeg"
    )
    raise AssertionError("unreachable")


def measure_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"ffprobe no pudo leer {path}:\n{result.stderr.strip()}")
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        fail(f"ffprobe devolvió una duración inválida para {path}: {result.stdout!r}")
    if duration <= 0:
        fail(f"El audio {path} tiene una duración no válida: {duration}")
    return round(duration, 3)


def cache_key(segment: Segment, voice: str, rate: str) -> str:
    payload = f"{segment.narration}\n{voice}\n{rate}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def synthesize(text: str, voice: str, rate: str, destination: Path) -> None:
    import edge_tts  # import perezoso: solo hace falta si no hay audio_file

    last_error: Exception | None = None
    for attempt in range(1, SYNTH_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
            await communicate.save(str(destination))
            if destination.exists() and destination.stat().st_size > 0:
                return
            raise RuntimeError("edge-tts generó un archivo vacío")
        except Exception as error:  # noqa: BLE001 - se reintenta y se reporta al final
            last_error = error
            if attempt < SYNTH_RETRIES:
                wait = 1.5 * attempt
                log(f"reintento {attempt}/{SYNTH_RETRIES - 1} para {destination.name} en {wait:.1f}s")
                await asyncio.sleep(wait)
    fail(
        "edge-tts no pudo generar la narración. Comprueba tu conexión a Internet "
        f"o usa `audio_file` en script.yaml.\nÚltimo error: {last_error}"
    )


def read_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        value = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Genera la narración de la demo de Croupier.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenera la voz aunque exista una caché válida.",
    )
    args = parser.parse_args()

    if not os.environ.get("DEMO_PDF"):
        log("DEMO_PDF no está definido; record.ts usará la ruta por defecto del README.")

    voice = os.environ.get("TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE
    rate = os.environ.get("TTS_RATE", DEFAULT_RATE).strip() or DEFAULT_RATE
    ffprobe = resolve_executable("ffprobe", "FFPROBE")

    segments = load_script()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    cache = read_cache()
    cache_updated = False
    output_segments: list[dict[str, Any]] = []

    log(f"voz={voice} rate={rate} segmentos={len(segments)}")

    for index, segment in enumerate(segments, start=1):
        if segment.audio_file:
            source = (DEMO_DIR / segment.audio_file).resolve()
            if not source.exists():
                fail(
                    f"`{segment.id}` apunta a audio_file={segment.audio_file!r}, "
                    f"pero no existe {source}."
                )
            audio_path = source
            kind = "grabación propia"
        else:
            audio_path = AUDIO_DIR / f"{segment.id}.mp3"
            key = cache_key(segment, voice, rate)
            cached = cache.get(segment.id)
            reusable = (
                not args.force
                and isinstance(cached, dict)
                and cached.get("hash") == key
                and audio_path.exists()
                and audio_path.stat().st_size > 0
            )
            if reusable:
                kind = "caché"
            else:
                log(f"({index}/{len(segments)}) sintetizando {segment.id}…")
                await synthesize(segment.narration, voice, rate, audio_path)
                cache[segment.id] = {
                    "hash": key,
                    "file": str(audio_path.relative_to(DEMO_DIR)),
                }
                cache_updated = True
                kind = "edge-tts"

        duration = measure_duration(ffprobe, audio_path)
        duration_ms = int(round(duration * 1000))
        segment_payload = {
            "index": index,
            "id": segment.id,
            "action": segment.action,
            "narration": segment.narration,
            "question": segment.question,
            "audio": str(audio_path),
            "audioFile": segment.audio_file,
            "duration": duration,
            "durationMs": duration_ms,
            "minDuration": round(duration + 0.6, 3),
            "minDurationMs": duration_ms + 600,
            "words": count_words(segment.narration),
            "kind": kind,
        }
        output_segments.append(segment_payload)
        log(
            f"  {segment.id:<18} {duration:6.2f}s  {segment_payload['words']:>2} palabras  ({kind})"
        )

    if cache_updated:
        write_json(CACHE_FILE, cache)

    total = round(sum(item["duration"] for item in output_segments), 3)
    payload = {
        "voice": voice,
        "rate": rate,
        "generatedAt": "deterministic",
        "totalAudio": total,
        "segments": output_segments,
    }
    write_json(SCRIPT_FILE, payload)
    write_json(
        DURATIONS_FILE,
        {
            "voice": voice,
            "rate": rate,
            "totalAudio": total,
            "byId": {item["id"]: item["duration"] for item in output_segments},
            "segments": [
                {"id": item["id"], "duration": item["duration"], "audio": item["audio"]}
                for item in output_segments
            ],
        },
    )

    log(f"audio total: {total:.2f}s ({total / 60:.2f} min)")
    log(f"escrito: {DURATIONS_FILE}")
    log(f"escrito: {SCRIPT_FILE}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        fail("interrumpido por el usuario")
