#!/usr/bin/env python3
"""Construye el plan temporal del video y los subtítulos SRT.

Entradas:
    demo/out/script.json    (lo escribe tts.py)
    demo/out/timeline.json  (lo escribe record.ts)

Salidas:
    demo/out/plan.json
    demo/out/subtitles.srt
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

DEMO_DIR = Path(__file__).resolve().parent
OUT_DIR = DEMO_DIR / "out"
SCRIPT_FILE = OUT_DIR / "script.json"
TIMELINE_FILE = OUT_DIR / "timeline.json"
PLAN_FILE = OUT_DIR / "plan.json"
SRT_FILE = OUT_DIR / "subtitles.srt"

MIN_VIDEO_SECONDS = 180.0
MAX_VIDEO_SECONDS = 270.0
CARD_PADDING = 0.6
SRT_MAX_LINE = 42
SRT_MAX_LINES = 2
MIN_CUE_SECONDS = 0.9


def fail(message: str) -> None:
    print(f"\n[plan] ERROR: {message}\n", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    if not path.exists():
        fail(f"No existe {path}. Ejecuta `make demo` para generarlo.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{path} no es JSON válido: {error}")


def format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_into_cues(text: str) -> list[str]:
    """Divide la narración en bloques de como máximo dos líneas de 42 caracteres."""
    text = " ".join(text.split())
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    cues: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        wrapped = textwrap.wrap(
            sentence,
            width=SRT_MAX_LINE,
            break_long_words=False,
            break_on_hyphens=False,
        )
        if not wrapped:
            continue
        # Agrupa frases cortas para no generar subtítulos de una sola palabra.
        candidate = current + wrapped
        if len(candidate) <= SRT_MAX_LINES:
            current = candidate
            continue
        if current:
            cues.append("\n".join(current))
        current = wrapped
        while len(current) > SRT_MAX_LINES:
            cues.append("\n".join(current[:SRT_MAX_LINES]))
            current = current[SRT_MAX_LINES:]
    if current:
        cues.append("\n".join(current))
    return cues


def build_srt(plan_segments: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    index = 1
    for segment in plan_segments:
        cues = split_into_cues(segment["narration"])
        if not cues:
            continue
        # Si hay demasiados cues para la duración, fusiona los últimos.
        duration = float(segment["duration"])
        while len(cues) > 1 and duration / len(cues) < MIN_CUE_SECONDS:
            cues[-2] = f"{cues[-2]}\n{cues[-1]}"
            cues.pop()
        weights = [max(1, len(cue.replace("\n", " "))) for cue in cues]
        total_weight = sum(weights)
        cursor = float(segment["start"])
        for cue_index, (cue, weight) in enumerate(zip(cues, weights, strict=True)):
            if cue_index == len(cues) - 1:
                end = float(segment["start"]) + duration
            else:
                end = cursor + duration * (weight / total_weight)
            start_time = cursor
            end_time = max(start_time + 0.35, end)
            blocks.append(
                f"{index}\n{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n{cue}\n"
            )
            index += 1
            cursor = end_time
    return "\n".join(blocks)


def main() -> None:
    script = load_json(SCRIPT_FILE)
    timeline = load_json(TIMELINE_FILE)

    script_segments = script.get("segments")
    timeline_segments = timeline.get("segments")
    if not isinstance(script_segments, list) or not script_segments:
        fail("script.json no contiene `segments`.")
    if not isinstance(timeline_segments, list) or not timeline_segments:
        fail("timeline.json no contiene `segments`.")

    timeline_by_id = {item["id"]: item for item in timeline_segments}
    app_ids = [item["id"] for item in script_segments if item["action"] not in {"intro", "outro"}]
    missing = [segment_id for segment_id in app_ids if segment_id not in timeline_by_id]
    if missing:
        fail(f"timeline.json no tiene los segmentos: {', '.join(missing)}")

    extra = [item["id"] for item in timeline_segments if item["id"] not in app_ids]
    if extra:
        fail(f"timeline.json contiene segmentos que no están en script.yaml: {', '.join(extra)}")

    plan_segments: list[dict[str, Any]] = []
    cursor = 0.0
    for script_segment in script_segments:
        segment_id = script_segment["id"]
        action = script_segment["action"]
        audio_duration = float(script_segment["duration"])
        if action in {"intro", "outro"}:
            kind = "card"
            duration = round(audio_duration + CARD_PADDING, 3)
        else:
            kind = "app"
            timed = timeline_by_id[segment_id]
            duration = round(float(timed["duration"]), 3)
            minimum = round(audio_duration + CARD_PADDING, 3)
            if duration + 0.08 < minimum:
                fail(
                    f"`{segment_id}` dura {duration:.2f}s en el video, pero necesita "
                    f"al menos {minimum:.2f}s (audio {audio_duration:.2f}s + 0.6s). "
                    "Vuelve a grabar con `make demo-record`."
                )

        plan_segments.append(
            {
                "index": len(plan_segments),
                "id": segment_id,
                "action": action,
                "kind": kind,
                "start": round(cursor, 3),
                "duration": duration,
                "audio": script_segment["audio"],
                "audioDuration": round(audio_duration, 3),
                "minDuration": round(audio_duration + CARD_PADDING, 3),
                "narration": script_segment["narration"],
            }
        )
        cursor += duration

    total = round(cursor, 3)
    app_duration = round(
        sum(item["duration"] for item in plan_segments if item["kind"] == "app"), 3
    )
    content_duration = round(float(timeline.get("contentDuration", 0)), 3)
    if abs(app_duration - content_duration) > 0.12:
        fail(
            f"El video de la app dura {content_duration:.2f}s, pero los segmentos suman "
            f"{app_duration:.2f}s. Vuelve a grabar con `make demo-record`."
        )

    if total < MIN_VIDEO_SECONDS or total > MAX_VIDEO_SECONDS:
        fail(
            f"El video final duraría {total:.1f}s ({total / 60:.2f} min). "
            f"El rango requerido es {MIN_VIDEO_SECONDS / 60:.0f}:00–"
            f"{MAX_VIDEO_SECONDS / 60:.1f} min. Ajusta las narraciones o los segmentos."
        )

    video = timeline.get("video")
    if not video:
        fail("timeline.json no apunta al video grabado (`video`).")

    plan = {
        "totalDuration": total,
        "appDuration": app_duration,
        "cardsDuration": round(total - app_duration, 3),
        "video": {
            "path": video,
            "contentStart": float(timeline.get("contentStart", 0)),
            "contentDuration": content_duration,
            "sourceDuration": timeline.get("videoDuration"),
        },
        "segments": plan_segments,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SRT_FILE.write_text(build_srt(plan_segments), encoding="utf-8")

    print(f"[plan] total: {total:.2f}s ({total / 60:.2f} min)")
    for segment in plan_segments:
        print(
            f"[plan] {segment['index']:>2} {segment['id']:<18} "
            f"{segment['start']:7.2f}s +{segment['duration']:6.2f}s  {segment['kind']}"
        )
    print(f"[plan] escrito: {PLAN_FILE}")
    print(f"[plan] escrito: {SRT_FILE}")


if __name__ == "__main__":
    main()
