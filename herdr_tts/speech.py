"""Playback: pick a player, play a WAV file, remember its PID so `stop` can
kill it, and dispatch the configured engine (piper / spd-say / command).

Audio comes out of the machine running the Herdr server.
"""

import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

from . import piper as piper_mod
from .log import log

# File players — handed a real .wav path (piping a 22 kHz WAV into a player that
# assumes 48 kHz is what makes it sound fast/chipmunk).
_PLAYERS = [
    ["paplay"],
    ["pw-play"],
    ["ffplay", "-hide_banner", "-loglevel", "error", "-autoexit", "-nodisp"],
    ["aplay", "-q"],
    ["afplay"],
    ["mpv", "--no-video", "--really-quiet"],
]


def herdr_bin():
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def toast(text):
    try:
        subprocess.run([herdr_bin(), "notification", "show", text],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _detect_player():
    for cand in _PLAYERS:
        if shutil.which(cand[0]):
            return cand
    return None


def _pidfile(state_dir):
    return Path(state_dir) / "play.pid"


def _kill_pgid(pgid):
    try:
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.15)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def stop(state_dir, engine="piper"):
    pf = _pidfile(state_dir)
    try:
        pgid = int(pf.read_text().strip())
        _kill_pgid(pgid)
        pf.unlink(missing_ok=True)
        log(state_dir, "stop: killed playback")
    except (FileNotFoundError, ValueError):
        log(state_dir, "stop: nothing playing")
    if engine == "spd-say" and shutil.which("spd-say"):
        subprocess.run(["spd-say", "-C"], check=False)


def _play_file(state_dir, wav):
    player = _detect_player()
    if not player:
        return False
    proc = subprocess.Popen(player + [str(wav)],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    _pidfile(state_dir).write_text(str(os.getpgid(proc.pid)))
    return True


def queue_clipboard(state_dir):
    """Queue a 'speak' with no text — the companion reads its own (client)
    clipboard. Used when the plugin runs on a remote server and a keybinding
    didn't carry the selection."""
    _spool(state_dir, "", from_clipboard=True)


def _spool(state_dir, text, from_clipboard=False):
    rec = {"t": round(time.time(), 3), "cmd": "speak", "text": text,
           "id": uuid.uuid4().hex[:12]}
    if from_clipboard:
        rec["from_clipboard"] = True
    sp = Path(state_dir) / "spool.jsonl"
    with sp.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    lines = sp.read_text(errors="replace").splitlines()
    if len(lines) > 200:
        sp.write_text("\n".join(lines[-200:]) + "\n")


def _cache_dir(state_dir):
    d = Path(state_dir) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    for old in sorted(d.glob("u-*.wav"))[:-3]:
        old.unlink(missing_ok=True)
    return d


def speak_text(config, config_dir, state_dir, text):
    """Synthesize + play `text`. Interrupts any current playback first."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    engine = config.get("engine", "piper")
    stop(state_dir, engine)

    if engine == "command":
        return _speak_command(config, state_dir, text)
    if engine == "spd-say":
        return _speak_spd(state_dir, text)
    if engine == "spool":
        _spool(state_dir, text)
        log(state_dir, f"speak: queued to spool ({len(text)} chars)")
        return "spool"
    return _speak_piper(config, config_dir, state_dir, text)


def _speak_piper(config, config_dir, state_dir, text):
    have_bin = piper_mod.piper_bin(config_dir, config.get("piper_bin", "")) is not None
    have_voice = piper_mod.voice_onnx(config_dir, config.get("voice", "en_US-ryan-high")) is not None
    if not (have_bin and have_voice):
        toast("herdr-tts: downloading Piper voice (first run)…")
    try:
        binary = piper_mod.ensure_piper(config_dir, config.get("piper_bin", ""),
                                        note=lambda m: log(state_dir, m))
        voice = piper_mod.ensure_voice(config_dir, config.get("voice", "en_US-ryan-high"),
                                       note=lambda m: log(state_dir, m))
    except piper_mod.PiperError as e:
        log(state_dir, f"piper unavailable: {e}")
        if shutil.which("spd-say"):
            toast("herdr-tts: Piper not set up — using spd-say. Run the setup pane.")
            return _speak_spd(state_dir, text)
        toast(f"herdr-tts: {e}")
        return "error"

    wav = _cache_dir(state_dir) / f"u-{int(time.time()*1000)}.wav"
    try:
        piper_mod.synth(binary, voice, text, wav, config.get("length_scale", 0.0))
    except piper_mod.PiperError as e:
        log(state_dir, str(e))
        toast("herdr-tts: synthesis failed")
        return "error"

    if _play_file(state_dir, wav):
        log(state_dir, f"speak: piper, {len(text)} chars")
        return "piper"
    # No audio device here (headless server) — hand off to the companion.
    if config.get("spool_fallback", True):
        _spool(state_dir, text)
        log(state_dir, f"speak: no player — queued to spool ({len(text)} chars)")
        return "spool"
    toast("herdr-tts: no audio player found")
    return "error"


def _speak_spd(state_dir, text):
    if not shutil.which("spd-say"):
        toast("herdr-tts: spd-say not installed")
        return "error"
    proc = subprocess.Popen(["spd-say", "-e", "-w", "--", text],
                            start_new_session=True)
    _pidfile(state_dir).write_text(str(os.getpgid(proc.pid)))
    log(state_dir, f"speak: spd-say, {len(text)} chars")
    return "spd-say"


def _speak_command(config, state_dir, text):
    argv = config.get("speak_command")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        toast("herdr-tts: engine=command but speak_command is not set")
        return "error"
    uses_ph = any("{text}" in a for a in argv)
    cmd = [a.replace("{text}", text) for a in argv]
    proc = subprocess.Popen(cmd,
                            stdin=None if uses_ph else subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    if not uses_ph:
        try:
            proc.stdin.write(text.encode("utf-8", "replace"))
            proc.stdin.close()
        except BrokenPipeError:
            pass
    _pidfile(state_dir).write_text(str(os.getpgid(proc.pid)))
    log(state_dir, f"speak: command {cmd[0]}, {len(text)} chars")
    return "command"


__all__ = ["speak_text", "stop", "toast"]
