#!/usr/bin/env bash
# herdr-tts — one-time setup on the CLIENT machine (your laptop).
#
# Installs: Piper + the en_US-ryan-high voice under ~/.local/share/herdr-tts/,
#           the listener at ~/.local/bin/herdr-tts-listend,
#           a starter config at ~/.config/herdr-tts/config.json,
#           and (optionally) a systemd --user service.
#
# Re-runnable: skips anything already present. Pass --force to re-download.

set -euo pipefail

PIPER_RELEASE="2023.11.14-2"
VOICE="en_US-ryan-high"
VOICE_HF_PATH="en/en_US/ryan/high"          # path under rhasspy/piper-voices
HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"
GH_BASE="https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}"

SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/herdr-tts"
BIN_DIR="$HOME/.local/bin"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/herdr-tts"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }

# --- arch / os --------------------------------------------------------------
os="$(uname -s)"; arch="$(uname -m)"
case "$os" in
  Linux)
    case "$arch" in
      x86_64)         piper_asset="piper_linux_x86_64.tar.gz" ;;
      aarch64|arm64)  piper_asset="piper_linux_aarch64.tar.gz" ;;
      armv7l)         piper_asset="piper_linux_armv7l.tar.gz" ;;
      *) warn "unknown arch '$arch' — install Piper manually into $SHARE/piper"; piper_asset="" ;;
    esac ;;
  Darwin)
    warn "macOS: download a piper_macos_*.tar.gz from"
    warn "  https://github.com/rhasspy/piper/releases/tag/${PIPER_RELEASE}"
    warn "extract it to $SHARE/piper/ , then re-run this script to fetch the voice."
    piper_asset="" ;;
  *) warn "unsupported OS '$os'"; piper_asset="" ;;
esac

mkdir -p "$SHARE/piper" "$SHARE/voices" "$BIN_DIR" "$CFG_DIR"

# --- piper binary ---------------------------------------------------------
if [[ -n "$piper_asset" ]]; then
  if [[ $FORCE -eq 1 || ! -x "$SHARE/piper/piper" ]]; then
    say "Downloading Piper ($piper_asset)"
    tmp="$(mktemp)"
    curl -fSL --retry 3 -o "$tmp" "$GH_BASE/$piper_asset"
    tar -xzf "$tmp" -C "$SHARE" && rm -f "$tmp"   # tarball contains a top-level piper/
    [[ -x "$SHARE/piper/piper" ]] || { warn "extract did not yield $SHARE/piper/piper"; exit 1; }
  else
    say "Piper already at $SHARE/piper/piper (use --force to re-download)"
  fi
fi

# --- voice model --------------------------------------------------------
for ext in onnx onnx.json; do
  dest="$SHARE/voices/${VOICE}.${ext}"
  if [[ $FORCE -eq 1 || ! -s "$dest" ]]; then
    say "Downloading voice ${VOICE}.${ext}"
    curl -fSL --retry 3 -o "$dest" "$HF_BASE/$VOICE_HF_PATH/${VOICE}.${ext}"
  else
    say "Voice ${VOICE}.${ext} already present"
  fi
done

# --- listener --------------------------------------------------------------
say "Installing listener -> $BIN_DIR/herdr-tts-listend"
install -m 0755 "$SRC_DIR/herdr-tts-listend" "$BIN_DIR/herdr-tts-listend"

# --- config -------------------------------------------------------------
cfg="$CFG_DIR/config.json"
if [[ ! -f "$cfg" ]]; then
  say "Writing starter config -> $cfg"
  cat > "$cfg" <<JSON
{
  "ssh_host": "my-herdr-host",
  "remote_spool": "~/.local/state/herdr/plugins/aktrov.herdr-tts/spool.jsonl",
  "engine": "piper",
  "piper_bin": "$SHARE/piper/piper",
  "piper_voice": "$SHARE/voices/${VOICE}.onnx",
  "piper_length_scale": null,
  "player": "auto",
  "max_chars": 4000
}
JSON
else
  say "Config already exists at $cfg — leaving it alone"
fi

# --- systemd --user unit (Linux) --------------------------------------
if [[ "$os" == "Linux" ]] && command -v systemctl >/dev/null 2>&1; then
  unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  mkdir -p "$unit_dir"
  sed "s#__BIN__#$BIN_DIR/herdr-tts-listend#g" \
      "$SRC_DIR/herdr-tts.service" > "$unit_dir/herdr-tts.service"
  say "Installed $unit_dir/herdr-tts.service"
  say "Enable it with:  systemctl --user daemon-reload && systemctl --user enable --now herdr-tts"
fi

# --- clipboard tool (for the keybinding path) ---------------------------
if ! command -v wl-paste >/dev/null 2>&1 \
   && ! command -v xclip >/dev/null 2>&1 \
   && ! command -v xsel  >/dev/null 2>&1 \
   && ! command -v pbpaste >/dev/null 2>&1; then
  warn "No clipboard reader found. The keyboard shortcut reads the clipboard"
  warn "(herdr doesn't hand the selection to keybindings). Install one:"
  warn "  Wayland:  sudo apt install wl-clipboard      X11:  sudo apt install xclip"
fi

# --- smoke test ------------------------------------------------------------
if [[ -x "$SHARE/piper/piper" && -s "$SHARE/voices/${VOICE}.onnx" ]]; then
  say "Speaking a test line (you should hear it now)…"
  "$BIN_DIR/herdr-tts-listend" -c "$cfg" --test \
    "Herdr text to speech is installed. Select some text in the terminal and press your shortcut." \
    || warn "test playback failed — check that one of pw-play / paplay / ffplay / aplay is installed"
fi

say "Done. Check the SSH host alias in $cfg (currently 'my-herdr-host'), then start the service."
