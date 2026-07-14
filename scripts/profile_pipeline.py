#!/usr/bin/env python3
"""Profile Listen Read pipeline phases and produce durable JSON/Markdown telemetry."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import resource
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any


SAMPLE_INTERVAL_SECONDS = 0.25


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def command_output(*command: str) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def byte_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, directories, files in os.walk(path):
        directories[:] = [name for name in directories if name != ".git"]
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def allocated_size(path: Path) -> int:
    if not path.exists():
        return 0
    output = command_output("du", "-sk", str(path))
    first = output.split(maxsplit=1)[0] if output else ""
    return int(first) * 1024 if first.isdigit() else 0


def host_context() -> dict[str, Any]:
    memory = command_output("sysctl", "-n", "hw.memsize")
    logical = command_output("sysctl", "-n", "hw.logicalcpu")
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "macOS": platform.mac_ver()[0],
        "chip": command_output("sysctl", "-n", "machdep.cpu.brand_string"),
        "logicalCpuCount": int(logical) if logical.isdigit() else os.cpu_count(),
        "memoryBytes": int(memory) if memory.isdigit() else None,
        "python": platform.python_version(),
        "energyTelemetry": {
            "captured": False,
            "reason": "powermetrics requires elevated privileges; no passwordless elevation is used",
        },
    }


def vm_memory() -> dict[str, int] | None:
    output = command_output("vm_stat")
    if not output:
        return None
    page_match = re.search(r"page size of (\d+) bytes", output)
    if not page_match:
        return None
    page_size = int(page_match.group(1))
    pages: dict[str, int] = {}
    for line in output.splitlines()[1:]:
        match = re.match(r"([^:]+):\s+([\d.]+)", line)
        if match:
            pages[match.group(1)] = int(float(match.group(2)))

    def total(*names: str) -> int:
        return sum(pages.get(name, 0) for name in names) * page_size

    return {
        "freeBytes": total("Pages free"),
        "reclaimableApproxBytes": total(
            "Pages free",
            "Pages inactive",
            "Pages speculative",
            "Pages purgeable",
        ),
        "wiredBytes": total("Pages wired down"),
        "compressedBytes": total("Pages occupied by compressor"),
    }


def process_rows() -> list[dict[str, float | int]]:
    output = command_output("ps", "-axo", "pid=,ppid=,%cpu=,rss=")
    rows: list[dict[str, float | int]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        try:
            rows.append(
                {
                    "pid": int(fields[0]),
                    "ppid": int(fields[1]),
                    "cpuPercent": float(fields[2]),
                    "rssBytes": int(fields[3]) * 1024,
                }
            )
        except ValueError:
            continue
    return rows


def descendant_rows(root_pid: int) -> list[dict[str, float | int]]:
    rows = process_rows()
    wanted = {root_pid}
    changed = True
    while changed:
        changed = False
        for row in rows:
            if int(row["ppid"]) in wanted and int(row["pid"]) not in wanted:
                wanted.add(int(row["pid"]))
                changed = True
    return [row for row in rows if int(row["pid"]) in wanted]


def load_report(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schemaVersion": 1,
        "createdAt": now_iso(),
        "host": host_context(),
        "samplingIntervalSeconds": SAMPLE_INTERVAL_SECONDS,
        "phases": [],
    }


def save_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def metric_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "samples": 0,
            "peakAggregateCpuPercent": 0.0,
            "meanAggregateCpuPercent": 0.0,
            "peakAggregateRssBytes": 0,
            "meanAggregateRssBytes": 0,
            "peakSingleProcessRssBytes": 0,
            "peakProcessCount": 0,
        }
    return {
        "samples": len(samples),
        "peakAggregateCpuPercent": round(max(item["cpuPercent"] for item in samples), 2),
        "meanAggregateCpuPercent": round(fmean(item["cpuPercent"] for item in samples), 2),
        "peakAggregateRssBytes": max(item["rssBytes"] for item in samples),
        "meanAggregateRssBytes": round(fmean(item["rssBytes"] for item in samples)),
        "peakSingleProcessRssBytes": max(item["singleRssBytes"] for item in samples),
        "peakProcessCount": max(item["processCount"] for item in samples),
    }


def run_phase(args: argparse.Namespace) -> int:
    report_path = args.report.resolve()
    report = load_report(report_path)
    phase_index = len(report["phases"]) + 1
    safe_name = re.sub(r"[^a-z0-9]+", "-", args.phase.casefold()).strip("-") or "phase"
    log_path = report_path.parent / "logs" / f"{phase_index:02d}-{safe_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = args.cwd.resolve() if args.cwd else Path.cwd()
    project = args.project.resolve() if args.project else None
    hf_cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
    disk_before = {
        "projectBytes": byte_size(project) if project else None,
        "huggingFaceCacheBytes": byte_size(hf_cache),
    }
    memory_before = vm_memory()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started_iso = now_iso()
    started = time.perf_counter()
    samples: list[dict[str, Any]] = []

    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            args.command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

        def pump_output() -> None:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read1(8192)
                if not chunk:
                    break
                log_file.write(chunk)
                log_file.flush()
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()

        output_thread = threading.Thread(target=pump_output, daemon=True)
        output_thread.start()
        while process.poll() is None:
            rows = descendant_rows(process.pid)
            samples.append(
                {
                    "elapsedSeconds": round(time.perf_counter() - started, 3),
                    "cpuPercent": sum(float(row["cpuPercent"]) for row in rows),
                    "rssBytes": sum(int(row["rssBytes"]) for row in rows),
                    "singleRssBytes": max((int(row["rssBytes"]) for row in rows), default=0),
                    "processCount": len(rows),
                    "systemMemory": vm_memory(),
                }
            )
            time.sleep(SAMPLE_INTERVAL_SECONDS)
        output_thread.join()
        exit_code = process.wait()

    ended = time.perf_counter()
    ended_iso = now_iso()
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall_seconds = ended - started
    user_seconds = usage_after.ru_utime - usage_before.ru_utime
    system_seconds = usage_after.ru_stime - usage_before.ru_stime
    disk_after = {
        "projectBytes": byte_size(project) if project else None,
        "huggingFaceCacheBytes": byte_size(hf_cache),
    }
    memory_after = vm_memory()
    reclaimable = [
        sample["systemMemory"]["reclaimableApproxBytes"]
        for sample in samples
        if sample.get("systemMemory")
    ]
    phase = {
        "name": args.phase,
        "command": args.command,
        "cwd": str(cwd),
        "startedAt": started_iso,
        "endedAt": ended_iso,
        "wallSeconds": round(wall_seconds, 3),
        "exitCode": exit_code,
        "log": str(log_path),
        "cpu": {
            "userSeconds": round(user_seconds, 3),
            "systemSeconds": round(system_seconds, 3),
            "totalSeconds": round(user_seconds + system_seconds, 3),
            "averageCoreEquivalent": round((user_seconds + system_seconds) / wall_seconds, 3)
            if wall_seconds
            else 0,
        },
        "processTree": metric_summary(samples),
        "systemMemory": {
            "before": memory_before,
            "after": memory_after,
            "minimumReclaimableApproxBytes": min(reclaimable) if reclaimable else None,
        },
        "disk": {
            "before": disk_before,
            "after": disk_after,
            "projectDeltaBytes": (
                disk_after["projectBytes"] - disk_before["projectBytes"]
                if project and disk_before["projectBytes"] is not None
                else None
            ),
            "huggingFaceCacheDeltaBytes": (
                disk_after["huggingFaceCacheBytes"] - disk_before["huggingFaceCacheBytes"]
            ),
        },
    }
    report["phases"].append(phase)
    save_report(report_path, report)
    print(
        f"\n[telemetry] {args.phase}: {wall_seconds:.2f}s, "
        f"peak RSS {format_bytes(phase['processTree']['peakAggregateRssBytes'])}, "
        f"CPU {phase['cpu']['totalSeconds']:.2f}s",
        file=sys.stderr,
    )
    return exit_code


def format_bytes(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_seconds(value: float) -> str:
    minutes, seconds = divmod(value, 60)
    return f"{int(minutes)}:{seconds:04.1f}" if minutes else f"{seconds:.2f}s"


def markdown_report(report: dict[str, Any]) -> str:
    overall = report["overall"]
    audio = report.get("audio", {})
    host = report["host"]
    lines = [
        "# Listen Read production profile",
        "",
        f"- Pipeline window: **{format_seconds(overall['pipelineWindowSeconds'])}**",
        f"- Measured command time: **{format_seconds(overall['measuredPhaseSeconds'])}**",
        f"- Narration: **{format_seconds(audio.get('durationSeconds', 0))}** for **{audio.get('wordCount', 0):,} words**",
        f"- Generation speed: **{audio.get('fasterThanRealTime', 0):.2f}× real time**",
        f"- Total child-process CPU time: **{format_seconds(overall['totalCpuSeconds'])}**",
        f"- Peak aggregate process RSS: **{format_bytes(overall['peakAggregateRssBytes'])}**",
        f"- Peak observed process-tree CPU: **{overall['peakAggregateCpuPercent']:.0f}%**",
        f"- Lowest approximate reclaimable system memory: **{format_bytes(overall['minimumReclaimableApproxBytes'])}**",
        f"- Host: **{host.get('chip')}**, {host.get('logicalCpuCount')} logical CPUs, {format_bytes(host.get('memoryBytes'))} unified memory",
        "",
        "## Phases",
        "",
        "| Phase | Wall | CPU time | Peak aggregate RSS | Mean RSS | Peak CPU | Disk change |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for phase in report["phases"]:
        process = phase["processTree"]
        lines.append(
            f"| {phase['name']} | {format_seconds(phase['wallSeconds'])} | "
            f"{format_seconds(phase['cpu']['totalSeconds'])} | "
            f"{format_bytes(process['peakAggregateRssBytes'])} | "
            f"{format_bytes(process['meanAggregateRssBytes'])} | "
            f"{process['peakAggregateCpuPercent']:.0f}% | "
            f"{format_bytes(phase['disk']['projectDeltaBytes'])} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts and model",
            "",
            f"- Reader directory: `{report['project']['path']}` ({format_bytes(report['project']['totalBytes'])})",
            f"- FLAC: {format_bytes(audio.get('flacBytes'))}",
            f"- Temporary chunk audio: {format_bytes(report['project']['components'].get('temporaryAudioBytes'))}",
            f"- Python environment: {format_bytes(report['project']['components'].get('pythonEnvironmentBytes'))}",
            f"- Node dependencies: {format_bytes(report['project']['components'].get('nodeModulesBytes'))}",
            f"- MLX peak Metal memory: {format_bytes(audio.get('mlxPeakMemoryBytes'))}",
            f"- Model cache: {'warm (no Hugging Face cache growth)' if audio.get('modelCacheWarm') else 'cold or changed'}",
            f"- Shared local model cache: {format_bytes(report['cache']['modelBytes'])} "
            f"(TTS {format_bytes(report['cache']['ttsModelBytes'])}, aligner {format_bytes(report['cache']['alignerModelBytes'])})",
            f"- Chunk cache hits: {audio.get('chunkCacheHits', 0)} of {audio.get('chunkCount', 0)}",
            f"- TTS revision: `{audio.get('modelRevision', '')}`",
            f"- Aligner revision: `{audio.get('alignerRevision', '')}`",
            f"- MLX-Audio revision: `{audio.get('mlxAudioRevision', '')}`",
            "",
            "Energy and GPU-utilization sampling are not included because macOS `powermetrics` requires elevated privileges. MLX Metal peak allocation and whole-process memory are captured instead.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize(args: argparse.Namespace) -> int:
    report_path = args.report.resolve()
    report = load_report(report_path)
    if not report["phases"]:
        raise RuntimeError("Cannot finalize an empty telemetry report")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    project = args.project.resolve()
    audio_relative = str(manifest["audio"]).split("?", 1)[0].lstrip("/")
    flac_path = project / "public" / audio_relative
    phases = report["phases"]
    first = datetime.fromisoformat(phases[0]["startedAt"])
    last = datetime.fromisoformat(phases[-1]["endedAt"])
    measured = sum(float(phase["wallSeconds"]) for phase in phases)
    total_cpu = sum(float(phase["cpu"]["totalSeconds"]) for phase in phases)
    minimum_reclaimable = [
        int(phase["systemMemory"]["minimumReclaimableApproxBytes"])
        for phase in phases
        if phase.get("systemMemory", {}).get("minimumReclaimableApproxBytes") is not None
    ]
    audio_phase = next((phase for phase in phases if phase["name"] == "audio_generation"), None)
    generation_wall = float(audio_phase["wallSeconds"]) if audio_phase else 0.0
    duration = float(manifest["duration"])
    word_count = int(manifest["wordCount"])
    generation_telemetry = manifest.get("generationTelemetry", {})
    report["overall"] = {
        "startedAt": phases[0]["startedAt"],
        "endedAt": phases[-1]["endedAt"],
        "pipelineWindowSeconds": round((last - first).total_seconds(), 3),
        "measuredPhaseSeconds": round(measured, 3),
        "unmeasuredCoordinationSeconds": round((last - first).total_seconds() - measured, 3),
        "totalCpuSeconds": round(total_cpu, 3),
        "peakAggregateRssBytes": max(
            int(phase["processTree"]["peakAggregateRssBytes"]) for phase in phases
        ),
        "peakAggregateCpuPercent": max(
            float(phase["processTree"]["peakAggregateCpuPercent"]) for phase in phases
        ),
        "minimumReclaimableApproxBytes": min(minimum_reclaimable)
        if minimum_reclaimable
        else None,
    }
    report["audio"] = {
        "durationSeconds": duration,
        "wordCount": word_count,
        "flacBytes": byte_size(flac_path),
        "generationWallSeconds": generation_wall,
        "realTimeFactor": round(generation_wall / duration, 4) if duration else None,
        "fasterThanRealTime": round(duration / generation_wall, 4) if generation_wall else None,
        "wordsPerGenerationMinute": round(word_count / generation_wall * 60, 2)
        if generation_wall
        else None,
        "voice": manifest.get("voice"),
        "model": manifest.get("model"),
        "modelRevision": manifest.get("modelRevision"),
        "aligner": manifest.get("aligner"),
        "alignerRevision": manifest.get("alignerRevision"),
        "mlxAudioRevision": manifest.get("mlxAudioRevision"),
        "mlxPeakMemoryBytes": generation_telemetry.get("mlxPeakMemoryBytes"),
        "modelCacheWarm": bool(audio_phase)
        and int(audio_phase["disk"]["huggingFaceCacheDeltaBytes"]) == 0,
        "chunkCacheHits": sum(
            1 for chunk in generation_telemetry.get("chunks", []) if chunk.get("cacheHit")
        ),
        "chunkCount": len(generation_telemetry.get("chunks", [])),
        "generatorBreakdown": generation_telemetry,
    }
    report["project"] = {
        "path": str(project),
        "totalBytes": byte_size(project),
        "components": {
            "pythonEnvironmentBytes": byte_size(project / ".venv"),
            "nodeModulesBytes": byte_size(project / "node_modules"),
            "temporaryAudioBytes": byte_size(project / "tmp" / "audio"),
            "publicAudioBytes": byte_size(project / "public" / "audio"),
            "buildBytes": byte_size(project / "dist"),
        },
    }
    hf_hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
    tts_cache = hf_hub / f"models--{str(manifest.get('model', '')).replace('/', '--')}"
    aligner_cache = hf_hub / f"models--{str(manifest.get('aligner', '')).replace('/', '--')}"
    report["cache"] = {
        "ttsModelBytes": allocated_size(tts_cache),
        "alignerModelBytes": allocated_size(aligner_cache),
        "modelBytes": allocated_size(tts_cache) + allocated_size(aligner_cache),
        "huggingFaceDeltaBytesDuringGeneration": int(
            audio_phase["disk"]["huggingFaceCacheDeltaBytes"] if audio_phase else 0
        ),
    }
    report["source"] = args.source
    save_report(report_path, report)
    archive = args.archive.resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, archive)
    markdown_path = args.markdown.resolve()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = markdown_report(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="action", required=True)

    run = subcommands.add_parser("run", help="Run and profile one pipeline phase")
    run.add_argument("--report", required=True, type=Path)
    run.add_argument("--phase", required=True)
    run.add_argument("--cwd", type=Path)
    run.add_argument("--project", type=Path)
    run.add_argument("command", nargs=argparse.REMAINDER)

    finish = subcommands.add_parser("finalize", help="Add derived metrics and render Markdown")
    finish.add_argument("--report", required=True, type=Path)
    finish.add_argument("--project", required=True, type=Path)
    finish.add_argument("--manifest", required=True, type=Path)
    finish.add_argument("--source", required=True)
    finish.add_argument("--archive", required=True, type=Path)
    finish.add_argument("--markdown", required=True, type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.action == "run":
        if not args.command:
            raise SystemExit("run requires a command after --")
        if args.command[0] == "--":
            args.command = args.command[1:]
        raise SystemExit(run_phase(args))
    raise SystemExit(finalize(args))


if __name__ == "__main__":
    main()
