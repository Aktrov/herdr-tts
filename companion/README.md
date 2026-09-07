# companion — client-side listener for `herdr --remote`

**Status: WIP.** The plugin at the repo root is the supported path; it plays
audio on the machine running the Herdr server. This companion covers the case
where that machine isn't the one you're sitting at.

On the **server**, in the plugin's `config.toml`:

```toml
engine = "spool"          # or leave the default engine and spool_fallback = true
```

On the **client**:

```bash
./setup-laptop.sh                       # Piper + the listener + a systemd unit
systemctl --user enable --now herdr-tts
```

`herdr-tts-listend` runs `ssh <host> -- tail -n0 -F <plugin-state>/spool.jsonl`,
synthesizes each queued line with Piper, and plays it locally; a new line
interrupts the current one, a `stop` record cancels it. Config lives at
`~/.config/herdr-tts/config.json` — set `ssh_host: ""` to tail a local spool
with no SSH.
