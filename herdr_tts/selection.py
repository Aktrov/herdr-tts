"""Work out what text to speak.

Right-click "Speak selection" gives us HERDR_PLUGIN_CONTEXT_JSON.selected_text.
A keybinding does NOT (herdr 0.8.x) — so fall back to the clipboard, which
`copy_on_select` keeps equal to the last mouse selection.
"""

import json
import os
import shutil
import subprocess

_CLIPBOARD = [
    ["wl-paste", "--no-newline"],
    ["xclip", "-selection", "clipboard", "-o"],
    ["xsel", "--clipboard", "--output"],
    ["pbpaste"],
]


def _from_context():
    raw = os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "")
    if not raw:
        return "", "no-context"
    try:
        ctx = json.loads(raw)
    except json.JSONDecodeError:
        return "", "bad-context-json"
    val = ctx.get("selected_text")
    return (val or ""), ("context" if val else "context-empty")


def _from_clipboard():
    on_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    order = _CLIPBOARD if on_wayland else _CLIPBOARD[1:] + _CLIPBOARD[:1]
    for cmd in order:
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        text = r.stdout.decode("utf-8", "replace")
        if text.strip():
            return text, f"clipboard/{cmd[0]}"
    return "", "clipboard-empty"


def _truncate(text, max_chars):
    text = text.strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " . . . text truncated."
    return text


def from_context(max_chars=4000):
    """Selection Herdr passed in the invocation context (right-click menu)."""
    text, source = _from_context()
    return _truncate(text, max_chars), source


def from_clipboard(max_chars=4000):
    """This machine's clipboard — only correct when the plugin runs where the
    user is (a local `herdr`). For a remote server, let the companion do it."""
    text, source = _from_clipboard()
    return _truncate(text, max_chars), source


def resolve_text(max_chars=4000):
    """Context selection, else this machine's clipboard. '' if nothing usable."""
    text, source = from_context(max_chars)
    if not text:
        text, source = from_clipboard(max_chars)
    return text, source


__all__ = ["resolve_text", "from_context", "from_clipboard"]
