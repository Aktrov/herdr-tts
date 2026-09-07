# companion — client-side listener for `herdr --remote`

The plugin (repo root) plays audio on the machine running the Herdr **server**.
When you attach with `herdr --remote`, that's not the machine you're at — so run
this listener on your client.

## Setup

**Server:** `herdr plugin install Aktrov/herdr-tts`, then set `engine = "spool"`
in the plugin's `config.toml` (`herdr plugin config-dir aktrov.herdr-tts`).

**Client:**

```bash
git clone https://github.com/Aktrov/herdr-tts
herdr-tts/companion/setup-laptop.sh
systemctl --user enable --now herdr-tts
```

`setup-laptop.sh` installs Piper + a voice, `herdr-tts-listend` into
`~/.local/bin`, a `systemd --user` unit, and `~/.config/herdr-tts/config.json`.
Edit that config:

- `ssh_host` — your SSH alias for the server (must work non-interactively).
  Set it to `""` to tail a **local** spool instead (single-machine testing).
- `remote_spool` — defaults to
  `~/.local/state/herdr/plugins/aktrov.herdr-tts/spool.jsonl`.
- `engine` / `piper_*` / `player` / `clipboard_cmd` — see `config.example.json`.

## What it does

Runs `ssh <host> -- tail -n0 -F <spool>`, and for each queued record:

- `speak` with text → stream Piper into the local player.
- `speak` with no text (`from_clipboard`) → read the local clipboard, then speak.
- `stop` → kill playback.

A new `speak` interrupts the current one. Drops records older than
`stale_after_seconds`. Reconnects with backoff if the SSH tail dies.
