# voice-type

Win+H-style voice dictation for Ubuntu 24.04 GNOME (X11).

Press a global hotkey, speak in English, press it again. The transcribed text
is typed into whatever text field has focus (browser, terminal, editor, chat).

## Architecture

- `daemon.py` — long-running Python service. Loads the faster-whisper `medium`
  model once, listens on a Unix socket, records mic audio with `sounddevice`,
  transcribes, and types the result via `xdotool`.
- `voice-type-toggle` — tiny client bound to the GNOME hotkey. Sends one byte
  (`T`) to the daemon over the socket. State is kept inside the daemon, so a
  second press stops recording and triggers transcription.
- `voice-type.service` — systemd user unit; keeps the daemon alive and
  autostarts it at login.
- `install.sh` — does everything: apt deps, venv, files, service, hotkey,
  warmup. `install.sh --uninstall` removes everything.

```
Hotkey  --> voice-type-toggle  --(unix socket)-->  voice-type-daemon
                                                        |
                                          mic -> whisper -> xdotool type
```

## Install

```bash
cd voice-type
./install.sh
```

You will be prompted once for `sudo` (for the apt step). The first run also
downloads the Whisper `medium` model (~1.5 GB) into `~/.cache/huggingface/`.

## Use

1. Click into any text field.
2. Press `Super+Alt+H`. A toast says "Recording...".
3. Speak.
4. Press `Super+Alt+H` again. The text appears.

## Configuration

Environment variables read by the daemon (set via `systemctl --user edit voice-type`):

- `VOICE_TYPE_MODEL` — `tiny`, `base`, `small`, `medium` (default), `large-v3`.
- `VOICE_TYPE_COMPUTE` — `int8` (default), `int8_float16`, `float16`, `float32`.
- `VOICE_TYPE_LANG` — language code (default `en`).

After changing a setting:

```bash
systemctl --user restart voice-type
```

## Troubleshooting

- **No text typed** — check the daemon is running:
  `systemctl --user status voice-type`. Tail logs: `journalctl --user -u voice-type -f`.
- **`xdotool` types into wrong window** — make sure the target window had
  focus before you pressed the hotkey.
- **Hotkey conflicts** — change the binding in
  *Settings -> Keyboard -> View and Customize Shortcuts -> Custom Shortcuts*.
- **Wayland** — this build targets X11. On Wayland, swap `xdotool` for
  `ydotool` (which needs a uinput service).

## Uninstall

```bash
./install.sh --uninstall
```
# voice-type
