"""Resolve the plugin's config and state directories.

Herdr sets HERDR_PLUGIN_CONFIG_DIR / HERDR_PLUGIN_STATE_DIR for actions and
event hooks. Build commands and out-of-Herdr test runs don't get them, so we
fall back to `herdr plugin config-dir <id>` and finally to Herdr's fixed layout.
"""

import os
import subprocess
from pathlib import Path

from . import PLUGIN_ID


def _fixed_dirs():
    home = Path.home()
    return (
        home / ".config" / "herdr" / "plugins" / "config" / PLUGIN_ID,
        home / ".local" / "state" / "herdr" / "plugins" / PLUGIN_ID,
    )


def _config_dir_via_cli():
    herdr = os.environ.get("HERDR_BIN_PATH") or "herdr"
    try:
        r = subprocess.run([herdr, "plugin", "config-dir", PLUGIN_ID],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def resolve_dirs():
    """Return (config_dir, state_dir) as Paths, resolved independently."""
    env_cfg = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or ""
    env_state = os.environ.get("HERDR_PLUGIN_STATE_DIR") or ""
    fixed_cfg, fixed_state = _fixed_dirs()
    cfg = Path(env_cfg) if env_cfg else (_config_dir_via_cli() or fixed_cfg)
    state = Path(env_state) if env_state else fixed_state
    return cfg, state


__all__ = ["resolve_dirs", "PLUGIN_ID"]
