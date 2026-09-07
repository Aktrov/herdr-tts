"""Locate (and, on request, download) the Piper binary and a voice, and
synthesize text to a WAV file.

Managed layout, under the plugin config dir:
    piper/piper                     the binary + its bundled libs / espeak-ng-data
    voices/<name>.onnx  + .onnx.json
"""

import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

PIPER_RELEASE = "2023.11.14-2"
_GH = f"https://github.com/rhasspy/piper/releases/download/{PIPER_RELEASE}"
_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# name -> path under the piper-voices repo (add more as needed)
_VOICE_PATHS = {
    "en_US-ryan-high": "en/en_US/ryan/high",
    "en_US-ryan-medium": "en/en_US/ryan/medium",
    "en_US-lessac-medium": "en/en_US/lessac/medium",
    "en_US-lessac-high": "en/en_US/lessac/high",
    "en_US-amy-medium": "en/en_US/amy/medium",
    "en_US-kusal-medium": "en/en_US/kusal/medium",
    "en_GB-alan-medium": "en/en_GB/alan/medium",
    "en_GB-cori-high": "en/en_GB/cori/high",
}


class PiperError(RuntimeError):
    pass


def _asset():
    sys, mach = platform.system(), platform.machine().lower()
    if sys == "Linux":
        return {"x86_64": "piper_linux_x86_64.tar.gz",
                "aarch64": "piper_linux_aarch64.tar.gz",
                "arm64": "piper_linux_aarch64.tar.gz",
                "armv7l": "piper_linux_armv7l.tar.gz"}.get(mach)
    if sys == "Darwin":
        return "piper_macos_aarch64.tar.gz" if mach in ("arm64", "aarch64") else "piper_macos_x64.tar.gz"
    return None


def _download(url, dest, note=print):
    note(f"  fetching {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)


# ---- binary --------------------------------------------------------------

def piper_bin(config_dir, configured=""):
    if configured:
        p = Path(os.path.expanduser(configured))
        if p.exists():
            return p
    managed = Path(config_dir) / "piper" / "piper"
    if managed.exists():
        return managed
    found = shutil.which("piper")
    return Path(found) if found else None


def ensure_piper(config_dir, configured="", note=print):
    p = piper_bin(config_dir, configured)
    if p:
        return p
    asset = _asset()
    if not asset:
        raise PiperError(f"no prebuilt Piper for {platform.system()}/{platform.machine()}; "
                         "install `piper` on PATH or set piper_bin in config.toml")
    dest_dir = Path(config_dir) / "piper"
    with tempfile.TemporaryDirectory() as td:
        tarball = Path(td) / asset
        _download(f"{_GH}/{asset}", tarball, note)
        note("  extracting piper")
        with tarfile.open(tarball) as tf:
            tf.extractall(dest_dir.parent)   # tarball has a top-level piper/
    binary = dest_dir / "piper"
    if not binary.exists():
        raise PiperError(f"extract did not produce {binary}")
    binary.chmod(0o755)
    return binary


# ---- voice ---------------------------------------------------------------

def _voice_repo_path(name):
    if name in _VOICE_PATHS:
        return _VOICE_PATHS[name]
    # en_US-ryan-high -> en/en_US/ryan/high
    parts = name.split("-")
    if len(parts) >= 3 and "_" in parts[0]:
        lang, speaker, quality = parts[0], "-".join(parts[1:-1]), parts[-1]
        return f"{lang.split('_')[0]}/{lang}/{speaker}/{quality}"
    return None


def voice_onnx(config_dir, voice):
    if voice.endswith(".onnx"):
        p = Path(os.path.expanduser(voice))
        return p if p.exists() else None
    p = Path(config_dir) / "voices" / f"{voice}.onnx"
    return p if p.exists() else None


def voice_sample_rate(onnx_path, default=22050):
    """Sample rate from the voice's <name>.onnx.json, for raw playback."""
    try:
        meta = json.loads(Path(str(onnx_path) + ".json").read_text())
        return int(meta.get("audio", {}).get("sample_rate", default)) or default
    except (OSError, ValueError, TypeError):
        return default


def ensure_voice(config_dir, voice, note=print):
    p = voice_onnx(config_dir, voice)
    if p:
        return p
    if voice.endswith(".onnx"):
        raise PiperError(f"voice file not found: {voice}")
    repo_path = _voice_repo_path(voice)
    if not repo_path:
        raise PiperError(f"don't know where to download voice '{voice}' — "
                         "add it to config.toml as an absolute .onnx path")
    dest = Path(config_dir) / "voices" / f"{voice}.onnx"
    _download(f"{_HF}/{repo_path}/{voice}.onnx", dest, note)
    _download(f"{_HF}/{repo_path}/{voice}.onnx.json", dest.with_suffix(".onnx.json"), note)
    return dest


# ---- synth -------------------------------------------------------------

def synth(binary, voice_file, text, out_wav, length_scale=0.0):
    binary = Path(binary)
    cmd = [str(binary), "--model", str(voice_file), "--output_file", str(out_wav)]
    if length_scale and length_scale > 0:
        cmd += ["--length_scale", str(length_scale)]
    espeak_data = binary.parent / "espeak-ng-data"
    if espeak_data.is_dir():
        cmd += ["--espeak_data", str(espeak_data)]
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = str(binary.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    r = subprocess.run(cmd, input=text.encode("utf-8", "replace"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       env=env, timeout=120)
    if r.returncode != 0 or not Path(out_wav).exists() or Path(out_wav).stat().st_size < 64:
        raise PiperError("piper synth failed: "
                         + r.stderr.decode("utf-8", "replace")[:200])
    return Path(out_wav)


__all__ = ["PiperError", "piper_bin", "ensure_piper", "voice_onnx",
           "voice_sample_rate", "ensure_voice", "synth", "PIPER_RELEASE"]
