# voice-type

Voice typing for Ubuntu.

Press a keyboard shortcut, speak, press the shortcut again, and your words are typed into the app you are using.

This is similar to Windows voice typing, but for Ubuntu GNOME on X11.

## What This App Does

`voice-type` lets you dictate text into:

- a browser
- a text editor
- a terminal
- a chat app
- almost any text box

It uses your microphone, converts your speech to text, and types the result into the active window.

## Supported System

This project is tested for:

- Ubuntu 24.04
- GNOME desktop
- X11 session

Important: this version is made for X11. It may not work correctly on Wayland.

To check if you are using X11 or Wayland, run:

```bash
echo $XDG_SESSION_TYPE
```

If it prints `x11`, this app should work.

If it prints `wayland`, log out, click the gear icon on the login screen, choose an Ubuntu X11 session, and log in again.

## Install

Open the Terminal app and run these commands:

```bash
git clone https://github.com/ranga291257/voice-type.git
cd voice-type
./install.sh
```

During installation:

- Ubuntu may ask for your password.
- The app installs required Ubuntu packages.
- The app creates a private Python environment.
- The app downloads a Whisper speech model.

The first install can take several minutes because the speech model is large.

## How To Use

1. Click inside any place where you want text to appear.
2. Press `Super+Alt+H`.
3. Speak normally.
4. Press `Super+Alt+H` again.
5. Wait a moment. The text should appear.

On most keyboards, `Super` is the Windows key.

## Example

Click inside a browser search box, press `Super+Alt+H`, say:

```text
weather in Chennai today
```

Then press `Super+Alt+H` again. The app will type the text into the search box.

## Check If It Is Running

Run:

```bash
systemctl --user status voice-type
```

If it is working, you should see `active`.

To watch logs:

```bash
journalctl --user -u voice-type -f
```

Press `Ctrl+C` to stop watching logs.

## Change The Keyboard Shortcut

The default shortcut is:

```text
Super+Alt+H
```

You can change it in Ubuntu:

1. Open Settings.
2. Go to Keyboard.
3. Open Keyboard Shortcuts.
4. Find custom shortcuts.
5. Edit the `Voice typing toggle` shortcut.

## Uninstall

From the project folder, run:

```bash
./install.sh --uninstall
```

This removes the service, shortcut, and installed app files.

## Troubleshooting

### No Text Appears

Check if the service is running:

```bash
systemctl --user status voice-type
```

If it is not running, try:

```bash
systemctl --user restart voice-type
```

### The Text Goes To The Wrong Window

Before pressing the shortcut, click inside the text box where you want the words to appear.

### The Shortcut Does Not Work

Another app may already use the same shortcut. Change the shortcut in Ubuntu Settings.

### It Is Slow The First Time

The first run is slower because the speech model needs to load. After that, it should feel faster.

### It Does Not Work On Wayland

This app currently uses `xdotool`, which works best on X11. Wayland support needs a different typing method.

## For Developers

Main files:

- `install.sh` installs and removes the app.
- `daemon.py` runs in the background, records audio, transcribes speech, and types text.
- `voice-type-toggle` sends the start/stop command.
- `voice-type.service` starts the background service when you log in.

Basic flow:

```text
Keyboard shortcut -> voice-type-toggle -> daemon.py -> microphone -> Whisper -> typed text
```
