#!/usr/bin/env bash
# Regenerate voice comparison samples under ./samples/ (gitignored).
# Downloads the Piper x86_64 binary + a set of voices into ./vendor/ if missing,
# then synthesizes the same sentence with each so you can A/B them.
#
# Usage:  tools/gen-samples.sh [voice ...]
#   default voices: en_US-lessac-medium en_US-ryan-high en_GB-alan-medium en_US-amy-medium

set -euo pipefail
cd "$(dirname "$0")/.."

PIPER_RELEASE="2023.11.14-2"
GH="https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}/piper_linux_x86_64.tar.gz"
HF="https://huggingface.co/rhasspy/piper-voices/resolve/main"

declare -A VOICE_PATH=(
  [en_US-lessac-medium]="en/en_US/lessac/medium"
  [en_US-ryan-high]="en/en_US/ryan/high"
  [en_US-amy-medium]="en/en_US/amy/medium"
  [en_GB-alan-medium]="en/en_GB/alan/medium"
  [en_US-kusal-medium]="en/en_US/kusal/medium"
  [en_GB-cori-high]="en/en_GB/cori/high"
)

VOICES=("$@")
[[ ${#VOICES[@]} -eq 0 ]] && VOICES=(en_US-lessac-medium en_US-ryan-high en_GB-alan-medium en_US-amy-medium)

SENT="Optimus online. This is the Piper neural text to speech voice you would hear on your laptop when you select text in the terminal and press the shortcut. Numbers like 3, 14 and 2026 read fine, and it handles punctuation, pauses, and questions, does it not?"

mkdir -p vendor/voices samples

if [[ ! -x vendor/piper/piper ]]; then
  echo "==> fetching piper binary"
  curl -fSL --retry 3 -o /tmp/piper.tgz "$GH"
  tar -xzf /tmp/piper.tgz -C vendor && rm -f /tmp/piper.tgz
fi
export LD_LIBRARY_PATH="$PWD/vendor/piper:${LD_LIBRARY_PATH:-}"

for v in "${VOICES[@]}"; do
  p="${VOICE_PATH[$v]:-}"
  [[ -z "$p" ]] && { echo "!! unknown voice $v (add it to VOICE_PATH)"; continue; }
  for ext in onnx onnx.json; do
    [[ -s "vendor/voices/$v.$ext" ]] || curl -fSL --retry 3 -o "vendor/voices/$v.$ext" "$HF/$p/$v.$ext"
  done
  echo "==> $v"
  printf '%s\n' "$SENT" | vendor/piper/piper --model "vendor/voices/$v.onnx" \
      --espeak_data vendor/piper/espeak-ng-data --output_file "samples/$v.wav"
done

if command -v sox >/dev/null; then
  tmp="$(mktemp -d)"
  args=()
  for v in "${VOICES[@]}"; do
    [[ -s "samples/$v.wav" ]] || continue
    printf 'Voice: %s.\n' "${v//-/ }" | vendor/piper/piper --model "vendor/voices/$v.onnx" \
        --espeak_data vendor/piper/espeak-ng-data --output_file "$tmp/$v.lbl.wav" 2>/dev/null
    sox "$tmp/$v.lbl.wav" "samples/$v.wav" "$tmp/$v.full.wav" pad 0 0.6
    args+=("$tmp/$v.full.wav")
  done
  sox "${args[@]}" samples/ALL-voices-compare.wav
  rm -rf "$tmp"
  echo "==> samples/ALL-voices-compare.wav"
fi

ls -la samples/
