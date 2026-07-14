from __future__ import annotations

from pathlib import Path
import shutil


def _bundled_skills() -> Path:
    packaged = Path(__file__).parent / "skills"
    checkout = Path(__file__).parents[2] / "skills"
    for candidate in (packaged, checkout):
        if (candidate / "listen-read" / "SKILL.md").is_file():
            return candidate
    raise FileNotFoundError("bundled Listen Read skills are missing")


def install_skills(targets: list[Path] | None = None, *, force: bool = False) -> dict:
    roots = targets or [Path.home() / ".codex" / "skills", Path.home() / ".claude" / "skills"]
    source = _bundled_skills()
    destinations = [root.expanduser() / name for root in roots for name in ("listen-read", "defuddle")]
    conflicts = [destination for destination in destinations if destination.exists()]
    if conflicts and not force:
        joined = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(
            f"skill folders already exist: {joined}; inspect them, then pass --force to replace them"
        )
    installed: list[str] = []
    for root in roots:
        root = root.expanduser()
        root.mkdir(parents=True, exist_ok=True)
        for name in ("listen-read", "defuddle"):
            destination = root / name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source / name, destination)
            installed.append(str(destination))
    return {"installed": installed}
