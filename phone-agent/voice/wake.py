"""
Wake / activation detection.

Four modes controlled by cfg.ACTIVATION_MODE:

  ptt     – Press Enter to start recording; silence ends it (default).
             Hold Enter for continuous recording; release to process.
  toggle  – Enter to start, Enter again to stop, regardless of silence.
  keyword – Vosk keyword spotting; say WAKE_WORD to start, SLEEP_WORD to stop.
  always  – No activation required; records continuously in a loop.

For PTT on Android you can map a hardware button to send a newline via
Termux:Tasker / Termux Widget, making it feel like a true PTT button.
"""

import json
import logging
import sys
import threading
import time
from typing import Callable, Optional

_log = logging.getLogger("nova.wake")


# ── PTT (terminal Enter key) ──────────────────────────────────────────────────

class PushToTalk:
    """
    Waits for Enter to be pressed in the terminal.
    Works in any Termux session; can be driven by a Tasker shortcut.
    """

    def __init__(self, agent_name: str = "Nova"):
        self.agent_name = agent_name

    def wait_for_press(self, prompt: str = "") -> bool:
        """Block until Enter. Returns False on Ctrl-C / EOF."""
        msg = prompt or f"  Press [Enter] to talk to {self.agent_name}, Ctrl-C to quit..."
        try:
            print(msg, end="", flush=True)
            input()
            return True
        except (EOFError, KeyboardInterrupt):
            return False

    def wait_for_second_press(self) -> bool:
        try:
            print("  Recording… press [Enter] to stop early.", end="", flush=True)
            input()
            return True
        except (EOFError, KeyboardInterrupt):
            return False


# ── Keyword / hotword detector (Vosk) ─────────────────────────────────────────

class KeywordDetector:
    """
    Lightweight always-on loop that listens for the wake word.
    Uses a grammar-restricted Vosk recognizer so CPU load is minimal.
    """

    def __init__(
        self,
        stt,                         # SpeechRecognizer instance
        recorder,                    # AudioRecorder instance (already open)
        wake_word: str,
        sleep_word: str,
        on_wake: Callable,           # called with no args when wake word heard
        on_sleep: Callable,          # called with no args when sleep word heard
    ):
        self.wake_word = wake_word.lower()
        self.sleep_word = sleep_word.lower()
        self.on_wake = on_wake
        self.on_sleep = on_sleep
        self._recorder = recorder
        self._active = False
        self._stop_event = threading.Event()

        # Narrow grammar for speed
        keywords = list({wake_word, sleep_word,
                         f"hey {wake_word}", f"okay {wake_word}", "[unk]"})
        self._kw_rec = stt.make_keyword_recognizer(keywords)

    def start(self):
        self._stop_event.clear()
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._stop_event.set()

    def _loop(self):
        import vosk
        while not self._stop_event.is_set():
            try:
                chunk = self._recorder.read_chunk()
                if self._kw_rec.AcceptWaveform(chunk):
                    text = json.loads(self._kw_rec.Result()).get("text", "").lower()
                    if not self._active and any(
                        w in text for w in [self.wake_word, f"hey {self.wake_word}"]
                    ):
                        self._active = True
                        self.on_wake()
                    elif self._active and self.sleep_word in text:
                        self._active = False
                        self.on_sleep()
            except Exception as e:
                _log.error("Keyword detection loop error: %s", e)
                time.sleep(0.05)


# ── Unified ActivationManager ─────────────────────────────────────────────────

class ActivationManager:
    """
    High-level wrapper that normalises all four modes into a consistent API:

        am.wait_for_activation()   → blocks until user wants to talk
        am.wait_for_deactivation() → blocks until user is done talking
    """

    def __init__(self, mode: str, agent_name: str = "Nova"):
        self.mode = mode.lower()
        self._ptt = PushToTalk(agent_name)
        self._activated = threading.Event()
        self._deactivate = threading.Event()
        self._kw_detector: Optional[KeywordDetector] = None

    def attach_keyword_detector(self, detector: KeywordDetector):
        self._kw_detector = detector
        detector.on_wake = self._activated.set
        detector.on_sleep = self._deactivate.set
        detector.start()

    def wait_for_activation(self) -> bool:
        """Returns True when the user is ready to speak; False to quit."""
        if self.mode == "always":
            return True

        if self.mode == "keyword":
            if self._kw_detector is None:
                raise RuntimeError("Keyword mode requires attach_keyword_detector()")
            self._activated.clear()
            self._activated.wait()
            return True

        if self.mode == "toggle":
            return self._ptt.wait_for_press()

        # ptt (default)
        return self._ptt.wait_for_press()

    def wait_for_deactivation(self) -> bool:
        """
        In toggle/keyword mode: blocks until stop signal.
        In ptt/always mode: returns immediately (silence detection handles end).
        """
        if self.mode == "toggle":
            return self._ptt.wait_for_second_press()
        if self.mode == "keyword":
            self._deactivate.clear()
            self._deactivate.wait(timeout=45)
            return True
        return True   # ptt / always — silence detection drives the end
