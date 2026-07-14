#!/usr/bin/env python3
"""Generate a natural local narration and exact word timings for the prepared article."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

import mlx.core as mx
import numpy as np
from huggingface_hub import model_info
from mlx_audio.stt import load as load_stt
from mlx_audio.tts.utils import load_model
from scipy.io import wavfile


ROOT = Path(__file__).resolve().parents[1]
ARTICLE_PATH = ROOT / "src/generated/article.json"
PUBLIC_AUDIO = ROOT / "public/audio"
TMP_AUDIO = ROOT / "tmp/audio"
CHUNK_CACHE = Path(os.environ.get("LISTEN_READ_CHUNK_CACHE", TMP_AUDIO))

TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16"
ALIGN_MODEL = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"
TTS_REVISION = os.environ.get("LISTEN_READ_TTS_REVISION")
ALIGN_REVISION = os.environ.get("LISTEN_READ_ALIGNER_REVISION")
VOICE = "Aiden"
STYLE = (
    "Read in a calm, warm, thoughtful and completely natural long-form narration "
    "style. Use measured pacing, subtle emphasis and brief pauses at punctuation. "
    "Sound engaged and human, never theatrical, breathless or like an announcer."
)
SILENCE_SECONDS = 0.28
WORD_RE = re.compile(r"[\w]+(?:[’'-][\w]+)*", re.UNICODE)


@dataclass
class AlignedWord:
    text: str
    start: float
    end: float


def current_model_revision(model: str) -> str:
    revision = model_info(model).sha
    if not revision:
        raise RuntimeError(f"Could not resolve the current revision for {model}")
    return revision


def mlx_audio_revision() -> str:
    direct_url = distribution("mlx-audio").read_text("direct_url.json")
    if direct_url:
        commit = json.loads(direct_url).get("vcs_info", {}).get("commit_id")
        if commit:
            return str(commit)
    raise RuntimeError("mlx-audio was not installed from a pinned Git revision")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "listening-document"


def normalize_word(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)


def map_alignment(
    displayed: list[dict[str, Any]],
    aligned: list[AlignedWord],
    duration_seconds: float,
) -> list[dict[str, Any]]:
    """Map forced-alignment words back to stable DOM token indices."""
    output: list[dict[str, Any]] = []
    align_pos = 0

    for display in displayed:
        target = normalize_word(str(display["text"]))
        match_pos = None
        for candidate_pos in range(align_pos, min(align_pos + 5, len(aligned))):
            if normalize_word(aligned[candidate_pos].text) == target:
                match_pos = candidate_pos
                break

        if match_pos is None:
            if output:
                previous = output[-1]
                start = float(previous["end"])
                end = start + 0.08
            elif aligned:
                start = aligned[0].start
                end = aligned[0].end
            else:
                start = end = 0.0
        else:
            item = aligned[match_pos]
            start, end = item.start, item.end
            align_pos = match_pos + 1

        start = min(start, max(duration_seconds - 0.02, 0.0))
        if output:
            start = max(start, float(output[-1]["start"]))
        end = min(max(end, start + 0.02), duration_seconds)

        output.append(
            {
                "index": int(display["index"]),
                "text": str(display["text"]),
                "start": round(start, 3),
                "end": round(end, 3),
            }
        )

    return output


def write_wav(path: Path, sample_rate: int, audio: np.ndarray) -> None:
    peak = max(float(np.max(np.abs(audio))), 1e-6)
    normalized = np.clip(audio / max(peak, 1.0), -1.0, 1.0)
    wavfile.write(path, sample_rate, (normalized * 32767).astype(np.int16))


def generate(force: bool) -> None:
    run_started = time.perf_counter()
    mx.reset_peak_memory()
    article = json.loads(ARTICLE_PATH.read_text())
    revision_started = time.perf_counter()
    tts_model_revision = TTS_REVISION or current_model_revision(TTS_MODEL)
    align_model_revision = ALIGN_REVISION or current_model_revision(ALIGN_MODEL)
    installed_mlx_revision = mlx_audio_revision()
    revision_seconds = time.perf_counter() - revision_started
    words_by_chunk: dict[int, list[dict[str, Any]]] = {}
    for word in article["words"]:
        words_by_chunk.setdefault(int(word["chunkIndex"]), []).append(word)

    PUBLIC_AUDIO.mkdir(parents=True, exist_ok=True)
    TMP_AUDIO.mkdir(parents=True, exist_ok=True)
    CHUNK_CACHE.mkdir(parents=True, exist_ok=True)

    print(f"Loading {TTS_MODEL}", flush=True)
    tts_load_started = time.perf_counter()
    tts = load_model(TTS_MODEL, revision=tts_model_revision)
    tts_load_seconds = time.perf_counter() - tts_load_started
    print(f"Loading {ALIGN_MODEL}", flush=True)
    aligner_load_started = time.perf_counter()
    aligner = load_stt(ALIGN_MODEL, revision=align_model_revision)
    aligner_load_seconds = time.perf_counter() - aligner_load_started
    sample_rate = int(tts.sample_rate)
    silence = np.zeros(int(sample_rate * SILENCE_SECONDS), dtype=np.float32)

    full_audio: list[np.ndarray] = []
    timings: list[dict[str, Any]] = []
    chunk_telemetry: list[dict[str, Any]] = []
    elapsed = 0.0

    for ordinal, chunk in enumerate(article["chunks"], start=1):
        chunk_id = int(chunk["index"])
        text = str(chunk["text"])
        cache_payload = json.dumps(
            {
                "text": text,
                "voice": VOICE,
                "settings": {
                    "style": STYLE,
                    "temperature": 0.75,
                    "top_p": 0.92,
                    "repetition_penalty": 1.08,
                    "max_tokens": 4096,
                    "language": "English",
                },
                "model_revision": tts_model_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        chunk_wav = CHUNK_CACHE / f"chunk-v1-{hashlib.sha256(cache_payload).hexdigest()}.wav"
        chunk_started = time.perf_counter()
        cache_hit = chunk_wav.exists() and not force
        synthesis_seconds = 0.0

        if cache_hit:
            try:
                cached_rate, cached_pcm = wavfile.read(chunk_wav)
                if cached_rate != sample_rate or cached_pcm.size == 0:
                    raise ValueError("invalid cached WAV")
            except (OSError, ValueError):
                chunk_wav.unlink(missing_ok=True)
                cache_hit = False

        if not cache_hit:
            print(
                f"[{ordinal}/{len(article['chunks'])}] Generating {chunk['kind']}: "
                f"{text[:72]}",
                flush=True,
            )
            synthesis_started = time.perf_counter()
            results = list(
                tts.generate(
                    text=text,
                    voice=VOICE,
                    instruct=STYLE,
                    lang_code="English",
                    temperature=0.75,
                    top_p=0.92,
                    repetition_penalty=1.08,
                    max_tokens=4096,
                    split_pattern="",
                )
            )
            synthesis_seconds = time.perf_counter() - synthesis_started
            if not results:
                raise RuntimeError(f"TTS returned no audio for chunk {chunk_id}")
            audio = np.concatenate([np.asarray(result.audio) for result in results])
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{chunk_wav.name}.", suffix=".wav", dir=CHUNK_CACHE
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                write_wav(temporary, sample_rate, audio.astype(np.float32))
                with temporary.open("rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(temporary, chunk_wav)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise

        loaded_rate, pcm = wavfile.read(chunk_wav)
        if loaded_rate != sample_rate:
            raise RuntimeError(f"Unexpected sample rate {loaded_rate} in {chunk_wav}")
        audio_float = pcm.astype(np.float32) / 32767.0

        alignment_started = time.perf_counter()
        alignment = aligner.generate(str(chunk_wav), text=text, language="English")
        alignment_seconds = time.perf_counter() - alignment_started
        aligned = [
            AlignedWord(item.text, float(item.start_time), float(item.end_time))
            for item in alignment
        ]
        mapped = map_alignment(
            words_by_chunk.get(chunk_id, []),
            aligned,
            len(audio_float) / sample_rate,
        )
        for item in mapped:
            item["start"] = round(float(item["start"]) + elapsed, 3)
            item["end"] = round(float(item["end"]) + elapsed, 3)
            timings.append(item)

        full_audio.append(audio_float)
        full_audio.append(silence)
        elapsed += len(audio_float) / sample_rate + SILENCE_SECONDS
        chunk_telemetry.append(
            {
                "index": chunk_id,
                "kind": str(chunk["kind"]),
                "wordCount": len(words_by_chunk.get(chunk_id, [])),
                "characters": len(text),
                "audioSeconds": round(len(audio_float) / sample_rate, 3),
                "cacheHit": cache_hit,
                "synthesisSeconds": round(synthesis_seconds, 3),
                "alignmentSeconds": round(alignment_seconds, 3),
                "totalSeconds": round(time.perf_counter() - chunk_started, 3),
            }
        )
        print(
            "LISTEN_READ_EVENT "
            + json.dumps(
                {
                    "type": "chunk_completed",
                    "ordinal": ordinal - 1,
                    "chunk_index": chunk_id,
                    "duration_seconds": round(len(audio_float) / sample_rate, 3),
                    "cache_hit": cache_hit,
                    "synthesis_seconds": round(synthesis_seconds, 3),
                    "alignment_seconds": round(alignment_seconds, 3),
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        mx.clear_cache()

    assembly_started = time.perf_counter()
    combined = np.concatenate(full_audio)
    audio_slug = slugify(str(article["metadata"]["title"]))
    wav_path = PUBLIC_AUDIO / f"{audio_slug}.wav"
    write_wav(wav_path, sample_rate, combined)

    manifest = {
        "audio": f"/audio/{wav_path.name}",
        "duration": round(len(combined) / sample_rate, 3),
        "sampleRate": sample_rate,
        "voice": VOICE,
        "model": TTS_MODEL,
        "modelRevision": tts_model_revision,
        "aligner": ALIGN_MODEL,
        "alignerRevision": align_model_revision,
        "mlxAudioRevision": installed_mlx_revision,
        "style": STYLE,
        "wordCount": len(timings),
        "words": timings,
    }
    manifest_path = PUBLIC_AUDIO / "timings.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # FLAC is substantially smaller while preserving the exact sample timeline.
    flac_path = PUBLIC_AUDIO / f"{audio_slug}.flac"
    flac_started = time.perf_counter()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-compression_level",
            "8",
            str(flac_path),
        ],
        check=True,
    )
    flac_seconds = time.perf_counter() - flac_started
    audio_revision = hashlib.sha256(flac_path.read_bytes()).hexdigest()[:12]
    manifest["audio"] = f"/audio/{flac_path.name}?v={audio_revision}"
    manifest["audioRevision"] = audio_revision
    manifest["generationTelemetry"] = {
        "totalWallSeconds": round(time.perf_counter() - run_started, 3),
        "revisionResolutionSeconds": round(revision_seconds, 3),
        "ttsModelLoadSeconds": round(tts_load_seconds, 3),
        "alignerLoadSeconds": round(aligner_load_seconds, 3),
        "chunkSynthesisSeconds": round(
            sum(item["synthesisSeconds"] for item in chunk_telemetry), 3
        ),
        "chunkAlignmentSeconds": round(
            sum(item["alignmentSeconds"] for item in chunk_telemetry), 3
        ),
        "assemblyAndManifestSeconds": round(time.perf_counter() - assembly_started, 3),
        "flacEncodingSeconds": round(flac_seconds, 3),
        "mlxPeakMemoryBytes": int(mx.get_peak_memory()),
        "mlxActiveMemoryBytes": int(mx.get_active_memory()),
        "mlxCacheMemoryBytes": int(mx.get_cache_memory()),
        "chunks": chunk_telemetry,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Wrote {flac_path} ({manifest['duration'] / 60:.1f} minutes) and "
        f"{len(timings)} word timings",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Regenerate cached chunks")
    args = parser.parse_args()
    generate(force=args.force)
