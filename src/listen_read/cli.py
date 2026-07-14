from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Sequence

from .app import create_runtime
from .config import Settings
from .doctor import report as doctor_report
from .network import expose_tailscale
from .runtime import Runtime
from .server import create_server
from .setup import install_dependencies, setup_plan
from .skills import install_skills


Writer = Callable[[str], None]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="listen-read", description="Local-first listening library")
    parser.add_argument("--home", help="runtime home (or LISTEN_READ_HOME)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="check compatibility without downloading models")

    setup = commands.add_parser("setup", help="install pinned local dependencies and models")
    setup.add_argument("--yes", action="store_true", help="confirm the disclosed downloads")
    setup.add_argument("--skip-model-download", action="store_true", help=argparse.SUPPRESS)
    setup.add_argument("--force", action="store_true", help="reinstall the pinned runtime")

    skill_install = commands.add_parser("install-skills", help="install Listen Read and Defuddle skills")
    skill_install.add_argument("--target", action="append", default=[], help="skills root; repeatable")
    skill_install.add_argument("--force", action="store_true", help="replace existing skill folders")

    serve = commands.add_parser("serve", help="serve the library")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--detach", action="store_true")

    expose = commands.add_parser("expose", help="add a private Tailscale Serve listener")
    expose.add_argument("--https-port", type=int, required=True)
    expose.add_argument("--local-port", type=int, default=None)

    add = commands.add_parser("add", help="add a source or prepared document")
    add.add_argument("source", nargs="?")
    source_group = add.add_mutually_exclusive_group()
    source_group.add_argument("--markdown", metavar="PATH", help="Markdown file, or - for stdin")
    source_group.add_argument("--prepared", metavar="PATH", help="prepared-document JSON")
    add.add_argument("--title")
    add.add_argument("--source-url")

    listing = commands.add_parser("list", help="list articles")
    listing.add_argument("--include-trashed", action="store_true")
    show = commands.add_parser("show", help="show an article")
    show.add_argument("article_id")
    for name in ("trash", "restore"):
        action = commands.add_parser(name, help=f"{name} an article")
        action.add_argument("article_id")
    purge = commands.add_parser("purge", help="permanently remove a trashed article")
    purge.add_argument("article_id")
    purge.add_argument("--yes", action="store_true", help="confirm permanent deletion")
    commands.add_parser("storage", help="report storage by category")
    clear = commands.add_parser("clear-cache", help="remove regenerable cached artifacts")
    clear.add_argument("scope", choices=("chunks", "models"))
    clear.add_argument("--yes", action="store_true", help="confirm cache removal")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: Writer | None = None,
    stdin: object | None = None,
) -> int:
    args = _parser().parse_args(argv)
    write = stdout or sys.stdout.write
    input_stream = stdin or sys.stdin
    settings = Settings.from_environment(home=args.home)

    try:
        if args.command == "doctor":
            data = doctor_report(settings.home)
            _emit(write, data, as_json=args.json)
            return 0 if data["supported"] else 2
        if args.command == "setup":
            if not args.yes:
                _emit(write, setup_plan(settings), as_json=args.json)
                return 3
            compatibility = doctor_report(settings.home)
            if not compatibility["supported"]:
                raise OSError("local narration requires macOS on Apple Silicon")
            data = install_dependencies(
                settings,
                download_models=not args.skip_model_download,
                force=args.force,
            )
            _emit(write, data, as_json=args.json)
            return 0
        if args.command == "install-skills":
            targets = [Path(value) for value in args.target] or None
            _emit(write, install_skills(targets, force=args.force), as_json=args.json)
            return 0
        if args.command == "expose":
            network_settings = Settings.from_environment(home=args.home, port=args.local_port)
            _emit(
                write,
                expose_tailscale(network_settings, https_port=args.https_port),
                as_json=args.json,
            )
            return 0
        if args.command == "serve":
            settings = Settings.from_environment(home=args.home, host=args.host, port=args.port)
            if args.detach:
                data = _detach(settings)
                _emit(write, data, as_json=args.json)
                return 0
            return _serve(settings, write, args.json)

        runtime = Runtime(settings)
        try:
            if args.command == "add":
                if args.markdown:
                    markdown = input_stream.read() if args.markdown == "-" else Path(args.markdown).read_text(encoding="utf-8")
                    data = runtime.submit_markdown(markdown, title=args.title, source_url=args.source_url)
                elif args.prepared:
                    prepared = json.loads(Path(args.prepared).read_text(encoding="utf-8"))
                    markdown = prepared.get("display_markdown", prepared.get("markdown", ""))
                    if not markdown:
                        raise ValueError("prepared document requires display_markdown or markdown")
                    data = runtime.submit_markdown(
                        markdown,
                        title=args.title or prepared.get("title"),
                        source_url=args.source_url or prepared.get("source_url"),
                        prepared_document=prepared,
                    )
                elif args.source:
                    if args.source.startswith(("http://", "https://")):
                        data = runtime.submit_source(args.source, title=args.title)
                    else:
                        markdown = Path(args.source).read_text(encoding="utf-8")
                        data = runtime.submit_markdown(markdown, title=args.title, source_url=args.source_url)
                else:
                    raise ValueError("provide a URL, Markdown path, --markdown, or --prepared")
            elif args.command == "list":
                data = {"articles": runtime.list_articles(include_trashed=args.include_trashed)}
            elif args.command == "show":
                data = runtime.get_article(args.article_id)
            elif args.command == "trash":
                data = runtime.trash(args.article_id)
            elif args.command == "restore":
                data = runtime.restore(args.article_id)
            elif args.command == "purge":
                if not args.yes:
                    raise ValueError("purge is permanent; pass --yes to confirm")
                runtime.purge(args.article_id)
                data = {"purged": args.article_id}
            elif args.command == "storage":
                data = {"storage": runtime.storage()}
            elif args.command == "clear-cache":
                if not args.yes:
                    raise ValueError("cache removal has regeneration costs; pass --yes to confirm")
                data = runtime.clear_cache(args.scope)
            else:
                raise ValueError(f"unknown command: {args.command}")
            _emit(write, data, as_json=args.json)
            return 0
        finally:
            runtime.close()
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
        data = {"error": type(error).__name__, "message": str(error)}
        _emit(write, data, as_json=True if args.json else False)
        return 1


def _emit(write: Writer, data: dict, *, as_json: bool) -> None:
    if as_json:
        write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
        return
    if "article" in data:
        write(f"{data['article']['title']}\n{data['article']['route']}\n")
    elif "articles" in data:
        for article in data["articles"]:
            write(f"{article['id']}  {article['status']:<10}  {article['title']}\n")
    else:
        write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _serve(settings: Settings, write: Writer, as_json: bool) -> int:
    runtime, dispatcher = create_runtime(settings)
    server = create_server(runtime, host=settings.host, port=settings.port)
    pid_file = settings.home / "runtime" / "server.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    def stop(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _emit(
        write,
        {"status": "serving", "url": f"http://{settings.host}:{server.server_port}", "pid": os.getpid()},
        as_json=as_json,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        dispatcher.close()
        runtime.close()
        pid_file.unlink(missing_ok=True)
    return 0


def _detach(settings: Settings) -> dict:
    settings.ensure_directories()
    pid_file = settings.home / "runtime" / "server.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text())
            os.kill(pid, 0)
            return {"status": "already_running", "url": f"http://{settings.host}:{settings.port}", "pid": pid}
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)
    log_path = settings.home / "logs" / "server.log"
    command = [
        sys.executable,
        "-m",
        "listen_read",
        "--home",
        str(settings.home),
        "serve",
        "--host",
        settings.host,
        "--port",
        str(settings.port),
    ]
    environment = os.environ.copy()
    package_parent = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (package_parent, environment.get("PYTHONPATH")) if part
    )
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    health = f"http://{settings.host}:{settings.port}/api/health"
    for _ in range(50):
        if process.poll() is not None:
            raise OSError(f"server exited during startup; see {log_path}")
        try:
            with urllib.request.urlopen(health, timeout=0.2) as response:
                if response.status == 200:
                    return {"status": "started", "url": f"http://{settings.host}:{settings.port}", "pid": process.pid}
        except OSError:
            time.sleep(0.1)
    process.terminate()
    raise OSError(f"server did not become healthy; see {log_path}")


def entrypoint() -> None:
    raise SystemExit(main())
