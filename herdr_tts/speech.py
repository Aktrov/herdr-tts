"""Playback: dispatch the configured engine, stream Piper straight to the
player so long text starts speaking fast, and make sure only one utterance
runs at a time.

Audio comes out of the machine running the Herdr server.
"""

import contextlib
import fcntl
import json
import os
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

from . import piper as piper_mod
from .log import log

# File players — given a real .wav path (a headerless stream into a player that
# assumes 48 kHz is what makes it sound chipmunk).
_FILE_PLAYERS = [
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


# ---- single-instance lock + pid tracking ------------------------------------

@contextlib.contextmanager
def _lock(state_dir, timeout=20.0):
    """Exclusive lock so two `speak` invocations can't spawn overlapping audio.
    On timeout, proceed anyway (a dropped request is worse than a rare overlap)."""
    path = Path(state_dir) / "speak.lock"
    fh = open(path, "a+")
    deadline = time.monotonic() + timeout
    got = False
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    log(state_dir, "speak.lock: timeout, proceeding without it")
                    break
                time.sleep(0.1)
        yield
    finally:
        if got:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _pidf(state_dir, name):
    return Path(state_dir) / name


def _record_pgid(state_dir, name, pid):
    try:
        _pidf(state_dir, name).write_text(str(os.getpgid(pid)))
    except (ProcessLookupError, OSError):
        pass


def _kill(state_dir, name):
    pf = _pidf(state_dir, name)
    try:
        pgid = int(pf.read_text().strip())
    except (FileNotFoundError, ValueError):
        return False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            break
        time.sleep(0.1)
    pf.unlink(missing_ok=True)
    return True


def stop(state_dir, engine="piper", relay=False):
    killed = _kill(state_dir, "play.pid") | _kill(state_dir, "synth.pid")
    if engine == "spd-say" and shutil.which("spd-say"):
        subprocess.run(["spd-say", "-C"], check=False)
    relayed = spool_stop(state_dir) if relay else False
    parts = []
    if killed:
        parts.append("killed local audio")
    if relayed:
        parts.append("queued stop for companion")
    log(state_dir, "stop: " + (", ".join(parts) if parts else "nothing running"))


# ---- players ---------------------------------------------------------------

def _file_player():
    for cand in _FILE_PLAYERS:
        if shutil.which(cand[0]):
            return cand
    return None


def _raw_player(sample_rate):
    """A player that takes raw s16le mono on stdin — lets us stream Piper."""
    sr = int(sample_rate or 22050)
    if shutil.which("pw-play"):
        return ["pw-play", f"--rate={sr}", "--channels=1", "--format=s16", "-"]
    if shutil.which("paplay"):
        return ["paplay", "--raw", f"--rate={sr}", "--channels=1", "--format=s16le"]
    if shutil.which("aplay"):
        return ["aplay", "-q", "-t", "raw", "-f", "S16_LE", f"-r{sr}", "-c1", "-"]
    if shutil.which("ffplay"):
        return ["ffplay", "-hide_banner", "-loglevel", "error", "-autoexit",
                "-nodisp", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-"]
    return None


# ---- spool (remote handoff) ---------------------------------------------

def queue_clipboard(state_dir):
    _spool(state_dir, "", from_clipboard=True)


def _spool_write(state_dir, rec):
    sp = Path(state_dir) / "spool.jsonl"
    with sp.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    lines = sp.read_text(errors="replace").splitlines()
    if len(lines) > 200:
        sp.write_text("\n".join(lines[-200:]) + "\n")


def _spool(state_dir, text, from_clipboard=False):
    rec = {"t": round(time.time(), 3), "cmd": "speak", "text": text,
           "id": uuid.uuid4().hex[:12]}
    if from_clipboard:
        rec["from_clipboard"] = True
    _spool_write(state_dir, rec)


def spool_stop(state_dir):
    """Tell a companion listener to stop. No-op if nothing has spooled here."""
    sp = Path(state_dir) / "spool.jsonl"
    if not sp.exists():
        return False
    _spool_write(state_dir, {"t": round(time.time(), 3), "cmd": "stop",
                             "id": uuid.uuid4().hex[:12]})
    return True


def _cache_dir(state_dir):
    d = Path(state_dir) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    for old in sorted(d.glob("u-*.wav"))[:-3]:
        old.unlink(missing_ok=True)
    return d


# ---- entry point -------------------------------------------------------

def speak_text(config, config_dir, state_dir, text):
    """Synthesize + play `text`, interrupting anything already running."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    engine = config.get("engine", "piper")

    stop(state_dir, engine)                 # preempt fast, before we queue for the lock
    with _lock(state_dir):
        stop(state_dir, engine)             # and kill anything a racer just started
        if engine == "command":
            return _speak_command(config, state_dir, text)
        if engine == "spd-say":
            return _speak_spd(state_dir, text)
        if engine == "spool":
            _spool(state_dir, text)
            log(state_dir, f"speak: queued to spool ({len(text)} chars)")
            return "spool"
        return _speak_piper(config, config_dir, state_dir, text)


# ---- engines --------------------------------------------------------------

def _piper_cmd(binary, voice, length_scale):
    cmd = [str(binary), "--model", str(voice)]
    if length_scale and length_scale > 0:
        cmd += ["--length_scale", str(length_scale)]
    espeak = Path(binary).parent / "espeak-ng-data"
    if espeak.is_dir():
        cmd += ["--espeak_data", str(espeak)]
    return cmd


def _piper_env(binary):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = (str(Path(binary).parent) + os.pathsep
                              + env.get("LD_LIBRARY_PATH", ""))
    return env


def _speak_piper(config, config_dir, state_dir, text):
    have = (piper_mod.piper_bin(config_dir, config.get("piper_bin", "")) is not None
            and piper_mod.voice_onnx(config_dir, config.get("voice", "en_US-ryan-high")) is not None)
    if not have:
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

    ls = config.get("length_scale", 0.0)
    pcmd = _piper_cmd(binary, voice, ls)
    env = _piper_env(binary)

    # Streaming: Piper -> raw player in one pipeline. Playback starts on the
    # first audio chunk, so a long paragraph doesn't sit silent while it
    # synthesizes the whole thing.
    raw = _raw_player(piper_mod.voice_sample_rate(voice))
    if raw:
        pipeline = shlex.join(pcmd + ["--output-raw"]) + " | " + shlex.join(raw)
        proc = subprocess.Popen(["sh", "-c", pipeline], stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True, env=env)
        try:
            proc.stdin.write(text.encode("utf-8", "replace"))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        _record_pgid(state_dir, "play.pid", proc.pid)
        log(state_dir, f"speak: piper (stream), {len(text)} chars")
        return "piper"

    # No raw-capable player: synth to a file, then play it.
    player = _file_player()
    if not player:
        if config.get("spool_fallback", True):
            _spool(state_dir, text)
            log(state_dir, f"speak: no player — queued to spool ({len(text)} chars)")
            return "spool"
        toast("herdr-tts: no audio player found")
        return "error"
    wav = _cache_dir(state_dir) / f"u-{int(time.time()*1000)}.wav"
    synth = subprocess.Popen(pcmd + ["--output_file", str(wav)],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, start_new_session=True, env=env)
    _record_pgid(state_dir, "synth.pid", synth.pid)
    _, err = synth.communicate(text.encode("utf-8", "replace"), timeout=180)
    _pidf(state_dir, "synth.pid").unlink(missing_ok=True)
    if synth.returncode != 0 or not wav.exists() or wav.stat().st_size < 64:
        log(state_dir, "piper synth failed: " + err.decode("utf-8", "replace")[:200])
        toast("herdr-tts: synthesis failed")
        return "error"
    proc = subprocess.Popen(player + [str(wav)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    _record_pgid(state_dir, "play.pid", proc.pid)
    log(state_dir, f"speak: piper (file), {len(text)} chars")
    return "piper"


def _speak_spd(state_dir, text):
    if not shutil.which("spd-say"):
        toast("herdr-tts: spd-say not installed")
        return "error"
    proc = subprocess.Popen(["spd-say", "-e", "-w", "--", text], start_new_session=True)
    _record_pgid(state_dir, "play.pid", proc.pid)
    log(state_dir, f"speak: spd-say, {len(text)} chars")
    return "spd-say"


def _speak_command(config, state_dir, text):
    argv = config.get("speak_command")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        toast("herdr-tts: engine=command but speak_command is not set")
        return "error"
    uses_ph = any("{text}" in a for a in argv)
    cmd = [a.replace("{text}", text) for a in argv]
    proc = subprocess.Popen(cmd, stdin=None if uses_ph else subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    if not uses_ph:
        try:
            proc.stdin.write(text.encode("utf-8", "replace"))
            proc.stdin.close()
        except BrokenPipeError:
            pass
    _record_pgid(state_dir, "play.pid", proc.pid)
    log(state_dir, f"speak: command {cmd[0]}, {len(text)} chars")
    return "command"


__all__ = ["speak_text", "stop", "toast"]
