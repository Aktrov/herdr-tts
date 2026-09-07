# herdr-tts

A [Herdr](https://herdr.dev) plugin that speaks the selected terminal text aloud
in a natural neural voice ([Piper](https://github.com/rhasspy/piper)).

Select text, press your shortcut, hear it. A second shortcut stops playback.

## Install

```bash
herdr plugin install Aktrov/herdr-tts
```

The install step downloads the Piper binary and the default voice
(`en_US-ryan-high`, ~110 MB) into the plugin's config directory. If you're
offline it installs anyway — open the **Herdr TTS setup** pane later to finish.

**Audio plays on the machine running the Herdr server.** With a local `herdr`
that's your machine and you're done. For `herdr --remote`, see
[Remote](#remote-herdr---remote) below.

## Use

Herdr (0.8.x) invokes plugin actions only from **keybindings** — there's no
right-click or menu entry. Herdr plugins also can't register keys themselves, so
add this to the `config.toml` of the machine running your Herdr **client**
(`~/.config/herdr/config.toml`):

  ```toml
  [[keys.command]]
  key = "prefix+t"
  type = "plugin_action"
  command = "aktrov.herdr-tts.speak"
  description = "TTS: speak selection"

  [[keys.command]]
  key = "prefix+shift+s"
  type = "plugin_action"
  command = "aktrov.herdr-tts.stop"
  description = "TTS: stop speaking"
  ```

  Then `herdr server reload-config` (or `prefix+shift+r`, or re-attach).

  Herdr doesn't hand the selection to a keybound action (0.8.x — `selected_text`
  in the invocation context is always empty), so the shortcut reads the
  **clipboard** instead. `copy_on_select = true` (the Herdr default) keeps the
  clipboard equal to your last mouse selection, so selecting then pressing the
  key does the obvious thing. Needs `wl-clipboard` (Wayland) or `xclip`/`xsel`
  (X11) on whichever machine plays the audio (the server for local `herdr`; the
  companion's machine for `engine = "spool"`).

## Configure

`herdr plugin config-dir aktrov.herdr-tts` prints the directory; drop a
`config.toml` there (see [`config.example.toml`](config.example.toml)). All keys
optional:

| key | default | meaning |
|---|---|---|
| `engine` | `piper` | `piper` \| `spd-say` \| `command` \| `spool` |
| `voice` | `en_US-ryan-high` | a downloadable voice name, or an absolute `.onnx` path |
| `length_scale` | `0.0` | speech rate; `0` = voice default, `>1` slower, `<1` faster |
| `max_chars` | `4000` | long selections are truncated |
| `piper_bin` | `""` | blank = managed copy, then `piper` on `PATH` |
| `speak_command` | — | `engine=command`: argv; `{text}` placeholder or stdin |
| `spool_fallback` | `true` | queue to `spool.jsonl` when local playback can't run |

Voices: <https://huggingface.co/rhasspy/piper-voices>. Try a few with
`tools/gen-samples.sh <name>...`.

## Actions

| action | id |
|---|---|
| Speak selection | `aktrov.herdr-tts.speak` |
| Stop speaking | `aktrov.herdr-tts.stop` |
| Test TTS voice | `aktrov.herdr-tts.test` |
| Herdr TTS setup (pane) | — |

Bind `speak`/`stop` to keys (above); run `test` from `herdr plugin action
invoke aktrov.herdr-tts.test` or bind it too.

## Remote (`herdr --remote`)

The plugin runs on the Herdr **server**; with `--remote` that's not the machine
you're sitting at, so it can't reach your speakers. Two options:

1. **Route audio over SSH** — set in `config.toml` on the server:
   ```toml
   engine = "command"
   speak_command = ["ssh", "my-laptop", "spd-say"]   # or ["ssh", "my-mac", "say"]
   ```
2. **Companion listener** — set `engine = "spool"` (or leave `spool_fallback`
   on) and run [`companion/herdr-tts-listend`](companion/) on your client
   machine. It tails the plugin's `spool.jsonl` over SSH and plays locally with
   Piper. See `companion/README` — this path is WIP.

Also note: with `herdr --remote` the client reads keybindings from the **local**
machine's config by default, or attach with `--remote-keybindings server`.

## Troubleshooting

| symptom | check |
|---|---|
| Nothing happens | `tts.log` in the plugin state dir (`herdr plugin config-dir …` → sibling `../../../state/herdr/plugins/<id>/`), or `herdr plugin log list --plugin aktrov.herdr-tts` |
| Robotic voice | `engine` fell back to `spd-say` — open the setup pane to finish the Piper download |
| Fast / chipmunk | a custom `player` is piping instead of taking a file path |
| `prefix+t` does nothing | keybinding is on the wrong machine — see [Use](#use) / [Remote](#remote-herdr---remote) |
| `prefix+t` speaks stale text | it reads the clipboard; re-select (with `copy_on_select` on, that refreshes it) |

## Development

```
herdr-plugin.toml     manifest (actions, [[build]], setup pane)
bin/tts.py            entrypoint: speak | stop | test
bin/setup.py          [[build]] + setup pane: fetch Piper + voice, write config
herdr_tts/
  paths.py            config/state dir resolution
  config.py           defaults + TOML load (tomllib, tiny fallback < 3.11)
  piper.py            locate/download Piper + voice, synth to WAV
  speech.py           engine dispatch, player detection, play, stop, spool
  selection.py        selected_text -> clipboard -> ""
  log.py              rotating log
companion/            client-side listener for `herdr --remote` (WIP)
tools/gen-samples.sh  regenerate voice A/B samples
tests/                python3 -m unittest discover -s tests
```

Stdlib only. `herdr plugin link .` for local dev (skips `[[build]]` — run
`python3 bin/setup.py` yourself).

## License

MIT — see [LICENSE](LICENSE).
