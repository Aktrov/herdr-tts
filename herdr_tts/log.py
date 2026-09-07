"""Tiny rotating log so `speak`/`stop` leave a trail without Herdr's UI."""

import time
from pathlib import Path

_MAX_BYTES = 64 * 1024


def log(state_dir, msg):
    try:
        p = Path(state_dir) / "tts.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > _MAX_BYTES:
            tail = p.read_text(errors="replace").splitlines()[-200:]
            p.write_text("\n".join(tail) + "\n")
        with p.open("a") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


__all__ = ["log"]
