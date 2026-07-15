from __future__ import annotations

from pathlib import Path
import shutil


BUNDLED_SKILL_NAMES = ("lazyread", "defuddle")
LEGACY_SKILL_NAMES = ("lazyreader", "listen-read")


def _bundled_skills() -> Path:
    packaged = Path(__file__).parent / "skills"
    checkout = Path(__file__).parents[2] / "skills"
    for candidate in (packaged, checkout):
        if (candidate / "lazyread" / "SKILL.md").is_file():
            return candidate
    raise FileNotFoundError("bundled Lazyread skills are missing")


def install_skills(targets: list[Path] | None = None, *, force: bool = False) -> dict:
    roots = [
        root.expanduser()
        for root in (
            targets
            or [
                Path.home() / ".codex" / "skills",
                Path.home() / ".claude" / "skills",
            ]
        )
    ]
    source = _bundled_skills()
    destinations = [root / name for root in roots for name in BUNDLED_SKILL_NAMES]
    conflicts = [
        destination
        for destination in destinations
        if destination.exists() or destination.is_symlink()
    ]
    if conflicts and not force:
        joined = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(
            f"skill folders already exist: {joined}; inspect them, then pass --force to replace them"
        )
    legacy_moves = [
        (root / name, root / f".{name}-backup")
        for root in roots
        for name in LEGACY_SKILL_NAMES
    ]
    backup_conflicts = [
        backup
        for legacy, backup in legacy_moves
        if (legacy.exists() or legacy.is_symlink())
        and (backup.exists() or backup.is_symlink())
    ]
    if backup_conflicts:
        joined = ", ".join(str(path) for path in backup_conflicts)
        raise FileExistsError(
            f"legacy skill backups already exist: {joined}; inspect them before retrying"
        )
    installed: list[str] = []
    retired: list[str] = []
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        for name in LEGACY_SKILL_NAMES:
            legacy = root / name
            if legacy.exists() or legacy.is_symlink():
                backup = root / f".{name}-backup"
                legacy.rename(backup)
                retired.append(str(backup))
        for name in BUNDLED_SKILL_NAMES:
            destination = root / name
            if destination.is_symlink():
                destination.unlink()
            elif destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source / name, destination)
            installed.append(str(destination))
    return {"installed": installed, "retired": retired}
