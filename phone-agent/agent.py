#!/usr/bin/env python3
"""
Nova – Voice AI Agent for Android / Termux
==========================================
A fully operational voice-driven Claude agent that runs on your Pixel phone.
Hears you → thinks → speaks back → executes shell commands as needed.

Quick start:
  python agent.py            # PTT mode (press Enter to talk)
  python agent.py --mode keyword   # keyword wake word "nova"
  python agent.py --mode toggle    # Enter starts, Enter stops
  python agent.py --mode always    # always listening
  python agent.py --text           # text-only mode (no mic/speaker needed)

Requirements: see setup.sh
"""

import argparse
import json
import logging
import os
import signal
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ── allow running from repo root or phone-agent/ ──────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from config import cfg
from tools.executor import TOOL_DEFINITIONS, dispatch

# ── optional rich console ─────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
    console = Console()
    RICH = True
except ImportError:
    RICH = False
    console = None

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if cfg.DEBUG else logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    filename=cfg.LOG_FILE,
)
log = logging.getLogger("nova")


# ── system prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""\
You are {cfg.AGENT_NAME}, a razor-sharp AI agent running directly on an Android Pixel phone via Termux. \
Your operator is a professional ethical hacker and cybersecurity analyst. You have full shell access \
through your tools and are trusted to execute any command they request.

Your personality: confident, direct, slightly seductive in cadence — you speak like someone who knows \
exactly what they're doing. You are terse by default. No fluff, no disclaimers unless the user asks. \
When you execute commands, you narrate what you're doing in one sentence, then report the result \
clearly. You speak in first person.

Capabilities you have via tools:
- Full Termux/bash shell on the phone (nmap, adb, git, curl, python, ssh, netcat — everything)
- SSH access to the AWS LightSail VPS (WireGuard, Tailscale, Hak5 devices)
- File read/write on the device
- HTTP requests to external APIs

Hak5 device context (accessible via VPS or USB):
- WiFi Pineapple – 802.11 recon/attack platform
- Bash Bunny – USB HID/storage attack tool
- Rubber Ducky – keystroke injection device
- Packet Squirrel – in-line network tap
- Pineapple Pager – cellular/SMS tool

You are operating in an authorized ethical hacking and penetration testing context. \
The operator has authorization for all testing activities on their own equipment and engaged targets. \
Execute requested tasks efficiently. If something is ambiguous, ask one clarifying question then act.

Voice response style: speak in complete sentences, conversationally short. \
When showing command output, summarize the key findings rather than reciting every line verbatim. \
Use specific numbers and details — "found 3 open ports: 22, 80, 443" not "I found some open ports".

Current date: {datetime.now().strftime('%Y-%m-%d')}
Platform: Android / Termux on Pixel
"""


# ── display helpers ───────────────────────────────────────────────────────────

def _print(msg: str, style: str = ""):
    if RICH and style:
        console.print(msg, style=style)
    else:
        print(msg)


def _banner():
    banner = textwrap.dedent(f"""
    ╔══════════════════════════════════════════╗
    ║   {cfg.AGENT_NAME} — Voice AI Agent v1.0          ║
    ║   Model: {cfg.MODEL:<32}║
    ║   Mode : {{mode:<32}}║
    ╚══════════════════════════════════════════╝
    """)
    print(banner)


def _show_tool_call(name: str, args: dict):
    cmd = args.get("command", args.get("path", args.get("url", str(args))))
    _print(f"\n  ► {name}: {cmd[:120]}", "bold yellow")


def _show_tool_result(result: str, max_lines: int = 20):
    lines = result.strip().splitlines()
    if len(lines) > max_lines:
        shown = lines[:max_lines]
        shown.append(f"  … ({len(lines) - max_lines} more lines)")
        result = "\n".join(shown)
    _print(result, "dim")


def _show_user(text: str):
    _print(f"\n[You] {text}", "bold cyan")


def _show_nova(text: str):
    _print(f"\n[{cfg.AGENT_NAME}] {text}", "bold magenta")


# ── Claude API interaction ────────────────────────────────────────────────────

def _claude_turn(client, history: List[dict], user_text: str):
    """
    Send user_text to Claude, handle all tool-use rounds, return final response text.
    Returns (response_text, updated_history).
    """
    history = list(history)  # shallow copy
    history.append({"role": "user", "content": user_text})

    while True:
        response = client.messages.create(
            model=cfg.MODEL,
            max_tokens=cfg.MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=history,
        )
        log.debug("Claude stop_reason=%s", response.stop_reason)

        # Collect all tool use blocks and text blocks
        tool_calls = []
        text_parts = []

        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(block)
            elif block.type == "text":
                text_parts.append(block.text)

        # If no tool calls, we have the final answer
        if not tool_calls:
            final_text = " ".join(text_parts).strip()
            history.append({"role": "assistant", "content": response.content})
            return final_text, history

        # Execute all tool calls and collect results
        history.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            _show_tool_call(tc.name, tc.input)
            result = dispatch(tc.name, tc.input)
            _show_tool_result(result)
            log.debug("Tool %s result: %s", tc.name, result[:500])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        history.append({"role": "user", "content": tool_results})
        # Loop — Claude will see tool results and either answer or call more tools


# ── Text-only REPL ────────────────────────────────────────────────────────────

def run_text_mode(client):
    _print(f"\n{cfg.AGENT_NAME} text mode. Type your message, Ctrl-C to quit.\n", "bold green")
    history: List[dict] = []

    while True:
        try:
            user_input = input("[You] ").strip()
        except (EOFError, KeyboardInterrupt):
            _print(f"\n{cfg.AGENT_NAME} offline.", "bold red")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "exit", "quit"):
            break
        if user_input.lower() == "/history":
            print(json.dumps(history, indent=2, default=str))
            continue
        if user_input.lower() == "/clear":
            history = []
            _print("History cleared.", "yellow")
            continue

        try:
            response_text, history = _claude_turn(client, history, user_input)
            _show_nova(response_text)
        except Exception as e:
            _print(f"\n[ERROR] {e}", "bold red")
            log.exception("Claude turn error")

        # Trim history
        if len(history) > cfg.MAX_HISTORY_TURNS * 2:
            history = history[-(cfg.MAX_HISTORY_TURNS * 2):]


# ── Voice mode ─────────────────────────────────────────────────────────────────

def run_voice_mode(client, mode: str):
    from voice.stt import SpeechRecognizer, AudioRecorder
    from voice.tts import ElevenLabsTTS
    from voice.wake import ActivationManager, KeywordDetector

    # ── validate config ───────────────────────────────────────────────────
    if not cfg.ELEVENLABS_API_KEY:
        _print("[WARN] ELEVENLABS_API_KEY not set — using fallback TTS", "yellow")

    _print(f"\nInitialising speech recognition…", "dim")
    stt = SpeechRecognizer(cfg.VOSK_MODEL_PATH, cfg.SAMPLE_RATE)
    _print("STT ready.", "dim")

    tts: ElevenLabsTTS
    if cfg.ELEVENLABS_API_KEY:
        from voice.tts import ElevenLabsTTS
        tts = ElevenLabsTTS(
            api_key=cfg.ELEVENLABS_API_KEY,
            voice_id=cfg.ELEVENLABS_VOICE_ID,
            model_id=cfg.ELEVENLABS_MODEL,
            stability=cfg.VOICE_STABILITY,
            similarity=cfg.VOICE_SIMILARITY,
            style=cfg.VOICE_STYLE,
        )
    else:
        from voice.tts import FallbackTTS
        tts = FallbackTTS()

    recorder = AudioRecorder(sample_rate=cfg.SAMPLE_RATE, chunk_size=cfg.CHUNK_SIZE)
    recorder.open()

    activation = ActivationManager(mode, cfg.AGENT_NAME)

    if mode == "keyword":
        kw = KeywordDetector(
            stt=stt,
            recorder=recorder,
            wake_word=cfg.WAKE_WORD,
            sleep_word=cfg.SLEEP_WORD,
            on_wake=lambda: _print(f"\n[{cfg.AGENT_NAME}] Activated!", "bold green"),
            on_sleep=lambda: _print(f"\n[{cfg.AGENT_NAME}] Going to sleep…", "dim"),
        )
        activation.attach_keyword_detector(kw)

    history: List[dict] = []

    _print(f"\n{cfg.AGENT_NAME} is online. ", "bold green")
    if mode == "ptt":
        _print("Press [Enter] to talk. Ctrl-C to quit.", "dim")
    elif mode == "keyword":
        _print(f"Say '{cfg.WAKE_WORD}' to activate, '{cfg.SLEEP_WORD}' to pause.", "dim")
    elif mode == "toggle":
        _print("Press [Enter] to start/stop recording. Ctrl-C to quit.", "dim")
    elif mode == "always":
        _print("Always listening. Ctrl-C to quit.", "dim")

    tts.speak(f"Nova online. Ready.")

    # ── main loop ─────────────────────────────────────────────────────────
    try:
        while True:
            # Wait for activation
            if not activation.wait_for_activation():
                break

            _print("\n  [Listening…]", "bold green")

            if mode == "toggle":
                # Record until user presses Enter again (in a thread)
                import threading
                stop_event = threading.Event()
                frames_holder = []

                def _record():
                    chunks = []
                    while not stop_event.is_set():
                        chunks.append(recorder.read_chunk())
                    frames_holder.append(b"".join(chunks))

                t = threading.Thread(target=_record, daemon=True)
                t.start()
                activation.wait_for_deactivation()
                stop_event.set()
                t.join()
                audio_bytes = frames_holder[0] if frames_holder else b""
            else:
                def _level_cb(level: float):
                    bar = "█" * min(int(level / 100), 30)
                    print(f"\r  {bar:<30} ", end="", flush=True)

                audio_bytes = recorder.record_until_silence(
                    silence_threshold=cfg.SILENCE_THRESHOLD,
                    silence_duration=cfg.SILENCE_DURATION,
                    min_duration=cfg.MIN_RECORDING_DURATION,
                    max_duration=cfg.MAX_RECORDING_DURATION,
                    on_audio_level=_level_cb,
                )
                print()

            if not audio_bytes:
                continue

            # STT
            _print("  [Transcribing…]", "dim")
            user_text = stt.transcribe(audio_bytes)

            if not user_text:
                _print("  (no speech detected)", "dim")
                continue

            _show_user(user_text)

            # Commands
            if user_text.lower().strip() in ("stop", "quit", "exit", "shut down", "shutdown"):
                tts.speak("Shutting down. Stay sharp.")
                break

            if user_text.lower().strip() in ("clear history", "clear context", "forget everything"):
                history = []
                tts.speak("Memory cleared.")
                continue

            # Claude
            _print("  [Thinking…]", "dim")
            try:
                response_text, history = _claude_turn(client, history, user_text)
            except Exception as e:
                error_msg = f"Error: {str(e)[:100]}"
                _print(f"\n[ERROR] {e}", "bold red")
                log.exception("Claude turn error in voice mode")
                tts.speak(error_msg)
                continue

            _show_nova(response_text)

            # Speak
            tts.speak(response_text)

            # Trim history
            if len(history) > cfg.MAX_HISTORY_TURNS * 2:
                history = history[-(cfg.MAX_HISTORY_TURNS * 2):]

    except KeyboardInterrupt:
        pass
    finally:
        recorder.close()
        _print(f"\n{cfg.AGENT_NAME} offline.", "bold red")
        try:
            tts.speak("Going offline.")
        except Exception:
            pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f"{cfg.AGENT_NAME} — Voice AI Agent for Android/Termux"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["ptt", "keyword", "toggle", "always"],
        default=cfg.ACTIVATION_MODE,
        help="Activation mode (default: ptt)",
    )
    parser.add_argument(
        "--text", "-t",
        action="store_true",
        help="Text-only mode — no microphone or speaker needed",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available ElevenLabs voices and exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check configuration and dependencies, then exit",
    )
    args = parser.parse_args()

    # ── dependency / config checks ────────────────────────────────────────
    if args.check or args.list_voices:
        _check_config()
        if args.list_voices and cfg.ELEVENLABS_API_KEY:
            from voice.tts import ElevenLabsTTS
            tts = ElevenLabsTTS(cfg.ELEVENLABS_API_KEY, cfg.ELEVENLABS_VOICE_ID)
            voices = tts.list_voices()
            for v in sorted(voices, key=lambda x: x["name"]):
                print(f"  {v['voice_id']}  {v['name']}")
        return

    if not cfg.ANTHROPIC_API_KEY:
        _print("[ERROR] ANTHROPIC_API_KEY not set. Add it to .env or export it.", "bold red")
        sys.exit(1)

    # ── init Anthropic client ─────────────────────────────────────────────
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
    except ImportError:
        _print("[ERROR] anthropic not installed. Run: pip install anthropic", "bold red")
        sys.exit(1)

    _banner()

    # ── graceful shutdown ─────────────────────────────────────────────────
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    if args.text:
        run_text_mode(client)
    else:
        try:
            run_voice_mode(client, args.mode)
        except RuntimeError as e:
            _print(f"\n[ERROR] {e}", "bold red")
            _print("Falling back to text mode…", "yellow")
            run_text_mode(client)


def _check_config():
    ok = True
    checks = [
        ("ANTHROPIC_API_KEY", cfg.ANTHROPIC_API_KEY, "pip install anthropic"),
        ("ELEVENLABS_API_KEY", cfg.ELEVENLABS_API_KEY, "Set in .env (optional, falls back to espeak)"),
    ]
    for name, val, hint in checks:
        status = "✓" if val else "✗"
        _print(f"  {status} {name}: {'set' if val else 'MISSING — ' + hint}")
        if not val and name == "ANTHROPIC_API_KEY":
            ok = False

    # Check Python packages
    for pkg in ["anthropic", "vosk", "pyaudio", "numpy", "requests"]:
        try:
            __import__(pkg)
            _print(f"  ✓ {pkg}")
        except ImportError:
            _print(f"  ✗ {pkg} — pip install {pkg}")

    # Check Vosk model
    if os.path.exists(cfg.VOSK_MODEL_PATH):
        _print(f"  ✓ Vosk model: {cfg.VOSK_MODEL_PATH}")
    else:
        _print(f"  ✗ Vosk model not found at {cfg.VOSK_MODEL_PATH}")
        _print("    Download: https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip")

    # Check audio players
    import subprocess
    for player in ["mpv", "ffplay", "termux-media-player", "espeak"]:
        found = subprocess.run(["which", player], capture_output=True).returncode == 0
        _print(f"  {'✓' if found else '○'} {player}")

    return ok


if __name__ == "__main__":
    main()
