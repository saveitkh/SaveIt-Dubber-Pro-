"""Converts an absolute filesystem path under one of the media volumes into the
public URL main.py serves it at, so API responses never leak server filesystem
layout to the frontend."""

import os

from app.config import OUTPUTS_DIR, UPLOADS_DIR, VOICES_DIR

_MOUNTS = [(str(OUTPUTS_DIR), "/media/outputs"), (str(UPLOADS_DIR), "/media/uploads"), (str(VOICES_DIR), "/media/voices")]


def to_media_url(path: str | None) -> str | None:
    if not path:
        return None
    for base, prefix in _MOUNTS:
        rel = os.path.relpath(path, base)
        if not rel.startswith(".."):
            return f"{prefix}/{rel}"
    return None
