#!/usr/bin/env python3
"""herdr-tts setup.

  setup.py --fetch     non-interactive: download Piper + the voice, write a
                       starter config.toml. Used as the plugin [[build]] step;
                       always exits 0 so a failed download can't abort install.
  setup.py             the "Herdr TTS setup" pane: same, then a spoken test and
                       the keybinding block to copy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herdr_tts import piper as piper_mod          # noqa: E402
from herdr_tts import speech                       # noqa: E402
from herdr_tts.config import load_config           # noqa: E402
from herdr_tts.paths import resolve_dirs           # noqa: E402

REPO = Path(__file__).resolve().parent.parent
KEYS_SNIPPET = (REPO / "config" / "herdr-keys.snippet.toml")


def write_starter_config(config_dir):
    dst = Path(config_dir) / "config.toml"
    if dst.exists():
        return dst, False
    dst.parent.mkdir(parents=True, exist_ok=True)
    example = REPO / "config.example.toml"
    dst.write_text(example.read_text() if example.exists() else "engine = \"piper\"\n")
    return dst, True


def fetch(config_dir, note):
    ok = True
    try:
        note("Piper binary:")
        b = piper_mod.ensure_piper(config_dir, load_config(config_dir).get("piper_bin", ""), note=note)
        note(f"  ok: {b}")
    except Exception as e:                       # noqa: BLE001 — never abort install
        note(f"  FAILED: {e}")
        ok = False
    try:
        voice = load_config(config_dir).get("voice", "en_US-ryan-high")
        note(f"Voice {voice}:")
        v = piper_mod.ensure_voice(config_dir, voice, note=note)
        note(f"  ok: {v}")
    except Exception as e:                       # noqa: BLE001
        note(f"  FAILED: {e}")
        ok = False
    return ok


def main():
    non_interactive = "--fetch" in sys.argv[1:]
    config_dir, state_dir = resolve_dirs()
    Path(config_dir).mkdir(parents=True, exist_ok=True)

    cfg_path, created = write_starter_config(config_dir)
    print(f"config: {cfg_path}" + ("  (created)" if created else "  (kept)"))

    ok = fetch(config_dir, note=print)

    if non_interactive:
        if not ok:
            print("\nherdr-tts: setup incomplete (offline?). Open the "
                  "'Herdr TTS setup' pane later to finish, or set piper_bin/voice "
                  "in config.toml.")
        return 0

    print("\n--- test ---")
    if ok:
        speech.speak_text(load_config(config_dir), config_dir, state_dir,
                          "Setup complete. This is the voice you will hear.")
        print("If you heard a voice, you're set.")
    else:
        print("Skipped — setup did not complete.")

    if load_config(config_dir).get("engine") == "spool":
        print("\n--- companion listener ---")
        print("engine = spool: this plugin only queues. On the machine you sit "
              "at, install the listener that plays the audio:")
        print("  git clone https://github.com/Aktrov/herdr-tts")
        print("  herdr-tts/companion/setup-laptop.sh")
        print("  systemctl --user enable --now herdr-tts")

    print("\n--- keyboard shortcut ---")
    print("herdr can't self-register keys. Add this to the config.toml of the "
          "machine running your herdr *client*")
    print("(for `herdr --remote`, that's the machine you sit at; or attach with "
          "--remote-keybindings server):\n")
    try:
        print(KEYS_SNIPPET.read_text())
    except OSError:
        print('[[keys.command]]\nkey = "prefix+t"\ntype = "plugin_action"\n'
              'command = "aktrov.herdr-tts.speak"\n')
    try:
        input("\nPress Enter to close this pane. ")
    except EOFError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
