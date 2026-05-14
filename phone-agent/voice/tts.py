"""
Text-to-speech via ElevenLabs streaming API.

Audio is piped directly into mpv (installed via Termux: pkg install mpv),
so speech begins playing within ~200 ms rather than waiting for the full clip.

Fallback chain if mpv is missing: ffplay → termux-media-player → espeak.
"""

import os
import subprocess
import tempfile
import threading
from typing import Dict, Iterator, List, Optional

import requests

_ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


def _which(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


class ElevenLabsTTS:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_turbo_v2_5",
        stability: float = 0.45,
        similarity: float = 0.85,
        style: float = 0.35,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.voice_settings = {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": True,
        }
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    # ── public ────────────────────────────────────────────────────────────

    def speak(self, text: str, blocking: bool = True) -> None:
        if not text.strip():
            return
        self.stop()
        try:
            self._stream_to_player(text, blocking)
        except Exception as e:
            print(f"[TTS] ElevenLabs error: {e} — falling back")
            self._fallback_speak(text)

    def stop(self) -> None:
        with self._lock:
            if self._proc:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=1)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None

    def list_voices(self):
        r = requests.get(
            f"{_ELEVENLABS_BASE}/voices",
            headers={"xi-api-key": self.api_key},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("voices", [])

    # ── internals ─────────────────────────────────────────────────────────

    def _audio_stream(self, text: str) -> Iterator[bytes]:
        r = requests.post(
            f"{_ELEVENLABS_BASE}/text-to-speech/{self.voice_id}/stream",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": self.model_id,
                "voice_settings": self.voice_settings,
                "output_format": "mp3_44100_128",
            },
            stream=True,
            timeout=30,
        )
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=4096):
            if chunk:
                yield chunk

    def _stream_to_player(self, text: str, blocking: bool) -> None:
        if _which("mpv"):
            player_cmd = ["mpv", "--no-video", "--really-quiet", "-"]
        elif _which("ffplay"):
            player_cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-"]
        else:
            # No streaming player found — save and play
            self._save_and_play(text)
            return

        with self._lock:
            self._proc = subprocess.Popen(
                player_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        def _feed():
            try:
                for chunk in self._audio_stream(text):
                    with self._lock:
                        if self._proc is None or self._proc.stdin is None:
                            break
                    self._proc.stdin.write(chunk)
                with self._lock:
                    if self._proc and self._proc.stdin:
                        self._proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        feeder = threading.Thread(target=_feed, daemon=True)
        feeder.start()

        if blocking:
            with self._lock:
                proc = self._proc
            if proc:
                proc.wait()

    def _save_and_play(self, text: str) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
            for chunk in self._audio_stream(text):
                f.write(chunk)
        try:
            for cmd in [
                ["termux-media-player", "play", path],
                ["play", path],
                ["aplay", path],
            ]:
                if _which(cmd[0]):
                    subprocess.run(cmd, capture_output=True)
                    return
            print(f"[TTS] No audio player found. Audio saved at: {path}")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _fallback_speak(self, text: str) -> None:
        for cmd in [
            ["espeak-ng", "-v", "en+f3", "-s", "140", text],
            ["espeak", "-v", "en+f3", "-s", "140", text],
            ["festival", "--tts"],
        ]:
            if _which(cmd[0]):
                if cmd[0] == "festival":
                    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    p.communicate(input=text.encode())
                else:
                    subprocess.run(cmd, capture_output=True)
                return
        print(f"[Nova] {text}")
