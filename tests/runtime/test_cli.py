from __future__ import annotations

import json
import os
import signal
import socket
import time
import urllib.request
from pathlib import Path

from listen_read.cli import main
from listen_read.pipeline import DocumentPipeline, acquire_markdown


def invoke(home: Path, *args: str) -> tuple[int, str]:
    output: list[str] = []
    code = main(["--home", str(home), "--json", *args], stdout=output.append)
    return code, "".join(output)


def test_json_flag_is_accepted_before_or_after_the_subcommand(tmp_path: Path) -> None:
    for args in (
        ["--home", str(tmp_path / "before"), "--json", "doctor"],
        ["--home", str(tmp_path / "after"), "doctor", "--json"],
    ):
        output: list[str] = []
        code = main(args, stdout=output.append)

        assert code in {0, 2}
        assert json.loads("".join(output))["downloads_started"] is False


def test_user_can_add_list_show_and_manage_an_article(tmp_path: Path) -> None:
    markdown = tmp_path / "source.md"
    markdown.write_text("# A useful paper\n\nHello from the article.\n", encoding="utf-8")

    code, raw = invoke(tmp_path / "home", "add", "--markdown", str(markdown))
    created = json.loads(raw)
    article_id = created["article"]["id"]

    assert code == 0
    assert created["article"]["title"] == "A useful paper"
    assert created["article"]["route"] == f"/read/{article_id}"
    assert created["job"]["state"] == "queued"

    assert json.loads(invoke(tmp_path / "home", "list")[1])["articles"][0]["id"] == article_id
    assert json.loads(invoke(tmp_path / "home", "show", article_id)[1])["article"]["markdown"].startswith("# A useful paper")

    assert json.loads(invoke(tmp_path / "home", "trash", article_id)[1])["article"]["status"] == "trashed"
    assert json.loads(invoke(tmp_path / "home", "restore", article_id)[1])["article"]["status"] == "processing"
    assert json.loads(invoke(tmp_path / "home", "trash", article_id)[1])["article"]["status"] == "trashed"
    assert json.loads(invoke(tmp_path / "home", "purge", article_id, "--yes")[1]) == {"purged": article_id}
    assert json.loads(invoke(tmp_path / "home", "list", "--include-trashed")[1]) == {"articles": []}


def test_storage_reports_durable_categories(tmp_path: Path) -> None:
    markdown = tmp_path / "source.md"
    markdown.write_text("# Storage\n\nSome words.", encoding="utf-8")
    invoke(tmp_path / "home", "add", "--markdown", str(markdown))

    storage = json.loads(invoke(tmp_path / "home", "storage")[1])["storage"]

    assert set(storage) == {"articles", "temporary_chunks", "models", "runtime", "trash", "total"}
    assert storage["articles"]["bytes"] > 0
    assert storage["total"]["bytes"] >= storage["articles"]["bytes"]


def test_cli_accepts_the_nested_prepared_document_contract(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared.json"
    document = DocumentPipeline().prepare(
        acquire_markdown("# Prepared title\n\nRead me.")
    )
    prepared.write_text(
        json.dumps(document.to_dict()),
        encoding="utf-8",
    )

    code, raw = invoke(tmp_path / "home", "add", "--prepared", str(prepared))
    created = json.loads(raw)

    assert code == 0
    assert created["article"]["title"] == "Prepared title"
    assert created["article"]["markdown"].startswith("# Prepared title")
    assert created["article"]["document"]["speech"]["policy"]["citations"] == "omit_numeric"


def test_cli_rejects_an_incomplete_nested_prepared_document(tmp_path: Path) -> None:
    prepared = tmp_path / "incomplete.json"
    prepared.write_text(
        json.dumps({"display": {"markdown": "# Incomplete"}, "speech": {"text": "Incomplete"}}),
        encoding="utf-8",
    )

    code, raw = invoke(tmp_path / "home", "add", "--prepared", str(prepared))

    assert code == 1
    assert json.loads(raw)["error"] == "KeyError"


def test_doctor_is_machine_readable_and_never_downloads_models(tmp_path: Path) -> None:
    code, raw = invoke(tmp_path / "home", "doctor")
    report = json.loads(raw)

    assert code in {0, 2}
    assert report["supported"] is (not report["blockers"])
    assert report["requirements"]["platform"] is (
        report["platform"]["system"] == "Darwin" and report["platform"]["machine"] == "arm64"
    )
    assert report["home"] == str(tmp_path / "home")
    assert report["downloads_started"] is False
    assert {"disk", "memory", "python", "node", "defuddle", "ffmpeg", "uv", "tailscale"} <= set(report["checks"])


def test_detached_server_becomes_healthy_and_records_its_pid(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    output: list[str] = []
    code = main(
        [
            "--home",
            str(tmp_path / "home"),
            "--json",
            "serve",
            "--port",
            str(port),
            "--detach",
        ],
        stdout=output.append,
    )
    started = json.loads("".join(output))
    try:
        assert code == 0
        assert started["status"] == "started"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
            assert json.loads(response.read()) == {"status": "ok", "version": "0.1.0"}
    finally:
        if "pid" in started:
            os.kill(started["pid"], signal.SIGTERM)
            for _ in range(30):
                if not (tmp_path / "home" / "runtime" / "server.pid").exists():
                    break
                time.sleep(0.1)


def test_clear_cache_removes_only_the_selected_regenerable_category(tmp_path: Path) -> None:
    home = tmp_path / "home"
    chunk = home / "cache" / "chunks" / "one.wav"
    model = home / "cache" / "models" / "weights.safetensors"
    chunk.parent.mkdir(parents=True)
    model.parent.mkdir(parents=True)
    chunk.write_bytes(b"chunk")
    model.write_bytes(b"model")

    cleared = json.loads(invoke(home, "clear-cache", "chunks", "--yes")[1])

    assert cleared == {"cleared": "chunks", "bytes_removed": 5}
    assert not chunk.exists()
    assert model.exists()
