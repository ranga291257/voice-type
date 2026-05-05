#!/usr/bin/env bash
# voice-type installer / uninstaller for Ubuntu 24.04 GNOME (X11).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE_DIR="$HOME/.local/share/voice-type"
BIN_DIR="$HOME/.local/bin"
SVC_DIR="$HOME/.config/systemd/user"
VENV_DIR="$SHARE_DIR/venv"
SVC_NAME="voice-type.service"

GS_BASE="org.gnome.settings-daemon.plugins.media-keys"
GS_KB_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-type/"
GS_KB_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
HOTKEY_BINDING="<Super><Alt>h"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[34m%s\033[0m\n' "$*"; }

install_apt_packages() {
  blue "[1/8] Installing apt packages (sudo required)"
  local pkgs=(xdotool portaudio19-dev python3-venv python3-pip libnotify-bin)
  local missing=()
  for p in "${pkgs[@]}"; do
    dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
  done
  if [ "${#missing[@]}" -eq 0 ]; then
    green "  all apt deps already installed"
    return
  fi
  echo "  installing: ${missing[*]}"
  sudo apt-get update -y
  sudo apt-get install -y "${missing[@]}"
}

create_venv() {
  blue "[2/8] Creating Python venv at $VENV_DIR"
  mkdir -p "$SHARE_DIR" "$BIN_DIR" "$SVC_DIR"
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
  fi
  "$VENV_DIR/bin/pip" install --upgrade pip wheel
  "$VENV_DIR/bin/pip" install \
    "faster-whisper>=1.0" \
    "sounddevice>=0.4" \
    "numpy>=1.26"
}

install_files() {
  blue "[3/8] Installing daemon and toggle client"
  install -m 0644 "$SRC_DIR/daemon.py" "$SHARE_DIR/daemon.py"
  install -m 0755 "$SRC_DIR/voice-type-toggle" "$BIN_DIR/voice-type-toggle"
  install -m 0644 "$SRC_DIR/voice-type.service" "$SVC_DIR/$SVC_NAME"
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) red "  warning: $BIN_DIR is not on PATH (the GNOME shortcut uses an absolute path so it still works)";;
  esac
}

enable_service() {
  blue "[4/8] Enabling systemd user service"
  systemctl --user daemon-reload
  # Forward needed env vars so xdotool + notify-send work from the daemon.
  systemctl --user import-environment DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR || true
  systemctl --user enable "$SVC_NAME"
}

warmup_model() {
  blue "[5/8] Warming up model (first run downloads ~1.5 GB; this may take a few minutes)"
  "$VENV_DIR/bin/python" "$SHARE_DIR/daemon.py" --warmup
}

start_service() {
  blue "[6/8] Starting daemon"
  systemctl --user restart "$SVC_NAME"
  sleep 2
  if systemctl --user is-active --quiet "$SVC_NAME"; then
    green "  daemon is active"
  else
    red "  daemon failed to start; check: journalctl --user -u $SVC_NAME -e"
    exit 1
  fi
}

set_hotkey() {
  blue "[7/8] Registering GNOME hotkey $HOTKEY_BINDING"
  if ! command -v gsettings >/dev/null; then
    red "  gsettings not found; skipping. Add the shortcut manually in Settings -> Keyboard."
    return
  fi
  local current
  current=$(gsettings get "$GS_BASE" custom-keybindings 2>/dev/null || echo "@as []")
  if [[ "$current" != *"$GS_KB_PATH"* ]]; then
    if [[ "$current" == "@as []" || "$current" == "[]" ]]; then
      gsettings set "$GS_BASE" custom-keybindings "['$GS_KB_PATH']"
    else
      local trimmed="${current%]}"
      gsettings set "$GS_BASE" custom-keybindings "${trimmed}, '$GS_KB_PATH']"
    fi
  fi
  gsettings set "$GS_KB_SCHEMA:$GS_KB_PATH" name "Voice typing toggle"
  gsettings set "$GS_KB_SCHEMA:$GS_KB_PATH" command "$BIN_DIR/voice-type-toggle"
  gsettings set "$GS_KB_SCHEMA:$GS_KB_PATH" binding "$HOTKEY_BINDING"
  green "  hotkey set: $HOTKEY_BINDING -> voice-type-toggle"
}

print_summary() {
  blue "[8/8] Done"
  cat <<EOF

  Hotkey:        Super+Alt+H (press to start, press again to stop)
  Daemon status: systemctl --user status $SVC_NAME
  Logs:          journalctl --user -u $SVC_NAME -f
  Toggle CLI:    $BIN_DIR/voice-type-toggle
  Uninstall:     $0 --uninstall

  Open any text field, press Super+Alt+H, speak in English, press it again.
EOF
}

uninstall_all() {
  blue "Uninstalling voice-type"
  systemctl --user disable --now "$SVC_NAME" 2>/dev/null || true
  rm -f "$SVC_DIR/$SVC_NAME"
  systemctl --user daemon-reload || true

  if command -v gsettings >/dev/null; then
    local current
    current=$(gsettings get "$GS_BASE" custom-keybindings 2>/dev/null || echo "@as []")
    if [[ "$current" == *"$GS_KB_PATH"* ]]; then
      local cleaned
      cleaned=$(python3 -c "import ast,sys; v=ast.literal_eval(sys.argv[1]); print([x for x in v if x!='$GS_KB_PATH'])" "$current" 2>/dev/null || echo "[]")
      gsettings set "$GS_BASE" custom-keybindings "$cleaned"
    fi
    gsettings reset-recursively "$GS_KB_SCHEMA:$GS_KB_PATH" 2>/dev/null || true
  fi

  rm -f "$BIN_DIR/voice-type-toggle"
  rm -rf "$SHARE_DIR"
  green "uninstall complete"
}

main() {
  if [ "${1:-}" = "--uninstall" ]; then
    uninstall_all
    return
  fi
  install_apt_packages
  create_venv
  install_files
  enable_service
  warmup_model
  start_service
  set_hotkey
  print_summary
}

main "$@"
