"""Central configuration - reads from environment / .env file."""

import os
from pathlib import Path

# Load .env if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Config:
    # ── Anthropic ──────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))

    # ── ElevenLabs ─────────────────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    # Rachel voice (warm, confident, feminine). Override with ELEVENLABS_VOICE_ID.
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    ELEVENLABS_MODEL: str = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")

    # ElevenLabs voice personality knobs (0.0 – 1.0)
    VOICE_STABILITY: float = float(os.getenv("VOICE_STABILITY", "0.45"))
    VOICE_SIMILARITY: float = float(os.getenv("VOICE_SIMILARITY", "0.85"))
    VOICE_STYLE: float = float(os.getenv("VOICE_STYLE", "0.35"))

    # ── Vosk STT ───────────────────────────────────────────────────────────
    VOSK_MODEL_PATH: str = os.getenv(
        "VOSK_MODEL_PATH",
        str(Path.home() / "vosk-model-small-en-us-0.15"),
    )

    # ── Wake / activation ──────────────────────────────────────────────────
    # Modes: "ptt" (push-to-talk, Enter key), "keyword" (vosk hotword),
    #        "toggle" (Enter starts, Enter stops), "always" (never sleeps)
    ACTIVATION_MODE: str = os.getenv("ACTIVATION_MODE", "ptt")
    WAKE_WORD: str = os.getenv("WAKE_WORD", "nova").lower()
    SLEEP_WORD: str = os.getenv("SLEEP_WORD", "sleep nova").lower()

    # ── Audio ──────────────────────────────────────────────────────────────
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "16000"))
    CHANNELS: int = 1
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1024"))
    SILENCE_THRESHOLD: float = float(os.getenv("SILENCE_THRESHOLD", "400"))
    SILENCE_DURATION: float = float(os.getenv("SILENCE_DURATION", "1.5"))
    MIN_RECORDING_DURATION: float = float(os.getenv("MIN_RECORDING_DURATION", "0.4"))
    MAX_RECORDING_DURATION: float = float(os.getenv("MAX_RECORDING_DURATION", "45.0"))

    # ── Agent personality ──────────────────────────────────────────────────
    AGENT_NAME: str = os.getenv("AGENT_NAME", "Nova")
    MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "30"))

    # ── VPS / networking ───────────────────────────────────────────────────
    VPS_HOST: str = os.getenv("VPS_HOST", "")
    VPS_USER: str = os.getenv("VPS_USER", "ubuntu")
    VPS_SSH_KEY: str = os.getenv("VPS_SSH_KEY", str(Path.home() / ".ssh" / "id_ed25519"))
    TAILSCALE_IP: str = os.getenv("TAILSCALE_IP", "")

    # ── Misc ───────────────────────────────────────────────────────────────
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
    LOG_FILE: str = os.getenv("LOG_FILE", str(Path.home() / ".nova_agent.log"))
    SAFE_MODE: bool = os.getenv("SAFE_MODE", "false").lower() in ("1", "true", "yes")


cfg = Config()
