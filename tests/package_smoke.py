"""Exercise only files installed from a built distribution."""

from __future__ import annotations

import json
from importlib.metadata import version
import subprocess
import tempfile
from pathlib import Path

import listen_read
from listen_read.setup import _packaged_file
from listen_read.skills import _bundled_skills


assert listen_read.__version__ == version("listen-read")
assert (_bundled_skills() / "listen-read" / "SKILL.md").is_file()
assert (_bundled_skills() / "defuddle" / "SKILL.md").is_file()
assert _packaged_file("worker-requirements.lock").is_file()
assert _packaged_file("defuddle-package/package-lock.json").is_file()
assert (Path(listen_read.__file__).parent / "web" / "index.html").is_file()
notices = (Path(listen_read.__file__).parent / "THIRD_PARTY_NOTICES.md").read_text()
assert "Copyright (c) 2026 Steph Ango (@kepano)" in notices

with tempfile.TemporaryDirectory() as home:
    result = subprocess.run(
        ["listen-read", "--home", home, "doctor", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

assert result.returncode in {0, 2}, result.stderr
assert json.loads(result.stdout)["downloads_started"] is False
