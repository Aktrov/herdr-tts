#!/usr/bin/env python3
"""herdr-tts entrypoint for the plugin actions.

    tts.py speak     speak the selection (or clipboard fallback)
    tts.py stop      stop the current playback
    tts.py test      speak a canned line
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herdr_tts.config import load_config          # noqa: E402
from herdr_tts.log import log                     # noqa: E402
from herdr_tts.paths import resolve_dirs          # noqa: E402
from herdr_tts import selection, speech           # noqa: E402

TEST_LINE = ("Herdr text to speech is working. This is the Piper neural voice "
             "you'll hear when you speak a selection.")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "speak"
    config_dir, state_dir = resolve_dirs()
    cfg = load_config(config_dir)

    if action == "stop":
        speech.stop(state_dir, cfg.get("engine", "piper"))
        return 0

    if action == "test":
        text, source = TEST_LINE, "test"
    elif action == "speak":
        maxc = cfg.get("max_chars", 4000)
        text, source = selection.from_context(maxc)
        if not text:
            # No selection in the context (keybinding). If we're queuing to a
            # companion, let IT read the clipboard — it runs where the user is.
            if cfg.get("engine") == "spool":
                speech.queue_clipboard(state_dir)
                log(state_dir, "speak: no context selection — queued clipboard request")
                return 0
            text, source = selection.from_clipboard(maxc)
    else:
        log(state_dir, f"unknown action: {action!r}")
        return 2

    if not text:
        log(state_dir, f"speak: nothing to say (source={source})")
        speech.toast("herdr-tts: no text selected")
        return 0

    log(state_dir, f"speak: source={source}, {len(text)} chars")
    speech.speak_text(cfg, config_dir, state_dir, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
