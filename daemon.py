#!/usr/bin/env python3
"""voice-type daemon: persistent STT service.

Listens on a Unix socket. A 'T' byte toggles recording. Audio captured from
the default mic via sounddevice is transcribed with faster-whisper and typed
into the focused window via xdotool.
"""

from __future__ import annotations

import logging
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"
BLOCK_SIZE = 1024

MODEL_SIZE = os.environ.get("VOICE_TYPE_MODEL", "medium")
COMPUTE_TYPE = os.environ.get("VOICE_TYPE_COMPUTE", "int8")
LANGUAGE = os.environ.get("VOICE_TYPE_LANG", "en")

RUNTIME_DIR = Path(
    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
)
SOCKET_PATH = RUNTIME_DIR / "voice-type.sock"

LOG = logging.getLogger("voice-type")


def notify(summary: str, body: str = "", urgency: str = "low") -> None:
    """Best-effort desktop toast. Never raises."""
    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=voice-type",
                f"--urgency={urgency}",
                "--expire-time=2000",
                summary,
                body,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


class Recorder:
    """Captures mic audio in a background thread into a list of frames."""

    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            LOG.warning("audio status: %s", status)
        with self._lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
        with self._lock:
            self._frames = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            callback=self._callback,
        )
        self._stream.start()
        LOG.info("recording started")

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._frames, axis=0).flatten()
            self._frames = []
        LOG.info("recording stopped: %.2fs", len(audio) / SAMPLE_RATE)
        return audio.astype(np.float32)


class Typer:
    """Types text into the focused X11 window via xdotool."""

    def __init__(self) -> None:
        if subprocess.run(
            ["which", "xdotool"], stdout=subprocess.DEVNULL
        ).returncode != 0:
            LOG.error("xdotool not found; install with apt install xdotool")

    def type_text(self, text: str) -> None:
        if not text:
            return
        LOG.info("typing %d chars", len(text))
        subprocess.run(
            ["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", text],
            check=False,
        )


class Daemon:
    def __init__(self) -> None:
        LOG.info("loading whisper model: %s (%s)", MODEL_SIZE, COMPUTE_TYPE)
        self.model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type=COMPUTE_TYPE,
        )
        LOG.info("model loaded")
        self.recorder = Recorder()
        self.typer = Typer()
        self.state = "idle"
        self.state_lock = threading.Lock()
        self.work_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_flag = threading.Event()
        threading.Thread(
            target=self._worker, name="transcriber", daemon=True
        ).start()

    def warmup(self) -> None:
        """Run a tiny transcription to JIT-warm the model and codepaths."""
        LOG.info("warming up model...")
        silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
        segments, _ = self.model.transcribe(
            silence, language=LANGUAGE, beam_size=1
        )
        list(segments)
        LOG.info("warmup complete")

    def _transition(self, new_state: str) -> None:
        with self.state_lock:
            LOG.info("state: %s -> %s", self.state, new_state)
            self.state = new_state

    def toggle(self) -> None:
        with self.state_lock:
            current = self.state
        if current == "idle":
            self._transition("recording")
            notify("Voice typing", "Recording... press hotkey again to stop")
            self.recorder.start()
        elif current == "recording":
            audio = self.recorder.stop()
            self._transition("transcribing")
            notify("Voice typing", "Transcribing...")
            self.work_queue.put(audio)
        else:
            LOG.info("toggle ignored in state=%s", current)

    def _worker(self) -> None:
        while not self._stop_flag.is_set():
            try:
                audio = self.work_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if audio.size < SAMPLE_RATE // 4:
                    LOG.info("audio too short, skipping")
                    notify("Voice typing", "Audio too short")
                    self._transition("idle")
                    continue
                segments, info = self.model.transcribe(
                    audio,
                    language=LANGUAGE,
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 300},
                )
                text = "".join(seg.text for seg in segments).strip()
                LOG.info("transcribed (lang=%s): %r", info.language, text)
                if text:
                    self._transition("typing")
                    self.typer.type_text(text)
                else:
                    notify("Voice typing", "No speech detected")
            except Exception:
                LOG.exception("transcription failed")
                notify("Voice typing", "Error during transcription", "critical")
            finally:
                self._transition("idle")

    def serve(self) -> None:
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o600)
        srv.listen(4)
        LOG.info("listening on %s", SOCKET_PATH)
        notify("Voice typing", "Daemon ready")
        try:
            while not self._stop_flag.is_set():
                conn, _ = srv.accept()
                with conn:
                    cmd = conn.recv(1)
                    if not cmd:
                        continue
                    if cmd == b"T":
                        self.toggle()
                        conn.sendall(b"OK\n")
                    elif cmd == b"S":
                        with self.state_lock:
                            state = self.state
                        conn.sendall(state.encode() + b"\n")
                    elif cmd == b"Q":
                        conn.sendall(b"BYE\n")
                        self._stop_flag.set()
                        break
                    else:
                        conn.sendall(b"ERR\n")
        finally:
            srv.close()
            try:
                SOCKET_PATH.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if "--warmup" in sys.argv:
        d = Daemon()
        d.warmup()
        return 0
    d = Daemon()
    d.warmup()
    d.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
