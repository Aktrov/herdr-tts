"""Load config.toml from the plugin config dir. All keys optional."""

import json
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

DEFAULTS = {
    "engine": "piper",              # piper | spd-say | command
    "voice": "en_US-ryan-high",     # name under voices/, or an absolute .onnx path
    "length_scale": 0.0,            # 0 = voice default; >1 slower, <1 faster
    "max_chars": 4000,
    "piper_bin": "",               # "" = managed copy in the config dir, then PATH
    "speak_command": None,          # engine=command: argv; {text} placeholder or stdin
    "spool_fallback": True,         # queue to spool.jsonl when local playback can't run
}


def _coerce(raw):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_coerce(p) for p in _split_top(inner)]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return json.loads(raw) if raw[0] == '"' else raw[1:-1]
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            pass
    return raw


def _split_top(s):
    """Split a comma list, ignoring commas inside quotes."""
    out, cur, quote = [], [], ""
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == ",":
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _strip_comment(line):
    """Drop a trailing # comment, ignoring # inside quotes."""
    quote = ""
    esc = False
    out = []
    for ch in line:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\" and quote == '"':
            out.append(ch)
            esc = True
            continue
        if ch in "\"'":
            if not quote:
                quote = ch
            elif quote == ch:
                quote = ""
            out.append(ch)
            continue
        if ch == "#" and not quote:
            break
        out.append(ch)
    return "".join(out).strip()


def _tiny_toml(text):
    """Flat `key = value` only. Lines under a [table] header are ignored —
    this plugin's config has no tables."""
    parsed = {}
    in_table = False
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line:
            continue
        if line.startswith("["):
            in_table = True
            continue
        if in_table or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and val.strip():
            try:
                parsed[key] = _coerce(val)
            except (ValueError, json.JSONDecodeError):
                pass
    return parsed


def load_config(config_dir):
    cfg = dict(DEFAULTS)
    path = Path(config_dir) / "config.toml"
    if not path.exists():
        return cfg
    try:
        if tomllib is not None:
            loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            loaded = _tiny_toml(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # tomllib raises TOMLDecodeError < ValueError
        loaded = {}
    for key in DEFAULTS:
        if key in loaded:
            cfg[key] = loaded[key]
    return cfg


__all__ = ["DEFAULTS", "load_config"]
