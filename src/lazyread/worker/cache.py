from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def chunk_cache_key(
    *,
    text: str,
    voice: str,
    settings: Mapping[str, Any],
    model_revision: str,
    mlx_audio_revision: str,
) -> str:
    """Content-address a synthesized chunk using every audible input."""

    payload = json.dumps(
        {
            "text": text,
            "voice": voice,
            "settings": dict(settings),
            "model_revision": model_revision,
            "mlx_audio_revision": mlx_audio_revision,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"chunk-v1-{hashlib.sha256(payload).hexdigest()}"
