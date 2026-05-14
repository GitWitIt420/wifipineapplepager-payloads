"""
Speech-to-text using Vosk (fully offline, fast, works in Termux).

Install in Termux:
    pip install vosk pyaudio numpy
    # Download model (~50 MB):
    cd ~ && wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip vosk-model-small-en-us-0.15.zip
"""

import json
import os
import time
from typing import Callable, List, Optional

import numpy as np


def _require(pkg: str, install: str):
    try:
        return __import__(pkg)
    except ImportError:
        raise RuntimeError(f"{pkg} not installed.\n  Run: {install}")


class SpeechRecognizer:
    def __init__(self, model_path: str, sample_rate: int = 16000):
        vosk = _require("vosk", "pip install vosk")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Vosk model not found: {model_path}\n"
                "Download: https://alphacephei.com/vosk/models\n"
                "  wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip\n"
                "  unzip vosk-model-small-en-us-0.15.zip -d ~/"
            )
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(model_path)
        self.sample_rate = sample_rate
        self._rec = vosk.KaldiRecognizer(self.model, sample_rate)

    def transcribe(self, audio_bytes: bytes) -> str:
        self._rec.AcceptWaveform(audio_bytes)
        result = json.loads(self._rec.FinalResult())
        self._rec.Reset()
        return result.get("text", "").strip()

    def process_chunk(self, chunk: bytes) -> Optional[str]:
        """Feed a chunk; returns finalized text when a phrase completes."""
        if self._rec.AcceptWaveform(chunk):
            text = json.loads(self._rec.Result()).get("text", "").strip()
            return text if text else None
        return None

    def make_keyword_recognizer(self, keywords: List[str]):
        """Return a lightweight recognizer limited to these keywords."""
        import vosk
        grammar = json.dumps(keywords + ["[unk]"])
        return vosk.KaldiRecognizer(self.model, self.sample_rate, grammar)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        pa_mod = _require("pyaudio", "pip install pyaudio  # or: pkg install python-pyaudio")
        self._pa = pa_mod.PyAudio()
        self._paInt16 = pa_mod.paInt16
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._stream = None

    # ── context manager ───────────────────────────────────────────────────

    def open(self):
        self._stream = self._pa.open(
            format=self._paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
        )
        return self

    def close(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *_):
        self.close()
        self._pa.terminate()

    # ── low-level ─────────────────────────────────────────────────────────

    def read_chunk(self) -> bytes:
        return self._stream.read(self.chunk_size, exception_on_overflow=False)

    @staticmethod
    def rms(chunk: bytes) -> float:
        a = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a ** 2))) if len(a) else 0.0

    # ── high-level ────────────────────────────────────────────────────────

    def record_until_silence(
        self,
        silence_threshold: float = 400.0,
        silence_duration: float = 1.5,
        min_duration: float = 0.4,
        max_duration: float = 45.0,
        on_audio_level: Optional[Callable[[float], None]] = None,
    ) -> bytes:
        """Record until silence is detected; return raw PCM bytes."""
        chunks_per_sec = self.sample_rate / self.chunk_size
        silence_needed = int(silence_duration * chunks_per_sec)
        min_chunks = int(min_duration * chunks_per_sec)
        max_chunks = int(max_duration * chunks_per_sec)

        frames: List[bytes] = []
        silent = 0

        while len(frames) < max_chunks:
            data = self.read_chunk()
            frames.append(data)
            level = self.rms(data)
            if on_audio_level:
                on_audio_level(level)
            if level < silence_threshold:
                silent += 1
            else:
                silent = 0
            if len(frames) > min_chunks and silent >= silence_needed:
                break

        return b"".join(frames)
