#!/data/data/com.termux/files/usr/bin/bash
# Nova Agent — Termux One-Shot Installer
# Run this once after cloning the repo:
#   chmod +x setup.sh && ./setup.sh
#
# What this does:
#   1. Updates Termux packages
#   2. Installs system-level audio/network tools
#   3. Installs Python packages
#   4. Downloads the Vosk speech model
#   5. Requests Android permissions
#   6. Creates a .env template if one doesn't exist
#   7. Creates a ~/nova shortcut command

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR="$HOME/vosk-model-small-en-us-0.15"
MODEL_ZIP="$HOME/vosk-model-small-en-us-0.15.zip"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
head() { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }

echo -e "${CYAN}"
cat << 'EOF'
  _   _  _____   _  __    _
 | \ | |/ _ \ \ / // \   | |
 |  \| | | | \ V // _ \  | |
 | |\  | |_| || |/ ___ \ |_|
 |_| \_|\___/ |_/_/   \_\(_)
 Voice AI Agent — Termux Installer
EOF
echo -e "${NC}"

# ── 1. Termux packages ────────────────────────────────────────────────────────
head "Updating Termux packages"
pkg update -y && pkg upgrade -y

head "Installing system dependencies"
pkg install -y \
    python \
    python-pyaudio \
    portaudio \
    mpv \
    ffmpeg \
    nmap \
    openssh \
    git \
    curl \
    wget \
    unzip \
    termux-api \
    espeak-ng \
    iproute2 \
    netcat-openbsd \
    tcpdump \
    termux-tools

log "System packages installed."

# ── 2. Python packages ─────────────────────────────────────────────────────────
head "Installing Python packages"
pip install --upgrade pip

pip install \
    anthropic \
    vosk \
    numpy \
    requests \
    python-dotenv \
    rich

# pyaudio usually comes from pkg install python-pyaudio, but try pip as fallback
pip install pyaudio 2>/dev/null || warn "pyaudio via pip failed — using system package (that's fine)"

log "Python packages installed."

# ── 3. Vosk model ─────────────────────────────────────────────────────────────
head "Vosk speech model"

if [ -d "$MODEL_DIR" ]; then
    log "Model already present at $MODEL_DIR — skipping download."
else
    log "Downloading model (~50 MB)…"
    wget -q --show-progress -O "$MODEL_ZIP" "$MODEL_URL"
    log "Extracting…"
    unzip -q "$MODEL_ZIP" -d "$HOME"
    rm -f "$MODEL_ZIP"
    log "Model ready at $MODEL_DIR"
fi

# ── 4. Android permissions ─────────────────────────────────────────────────────
head "Android permissions"

if command -v termux-microphone-record &>/dev/null; then
    log "Requesting microphone permission…"
    termux-microphone-record -d 1 &>/dev/null || true
    sleep 1
    termux-microphone-record -q &>/dev/null || true
    log "Microphone permission requested."
else
    warn "termux-api not available. Install the Termux:API Android app from F-Droid."
    warn "Then run: pkg install termux-api"
fi

# Storage permission
log "Requesting storage permission…"
termux-setup-storage 2>/dev/null || warn "termux-setup-storage not available."

# ── 5. .env file ───────────────────────────────────────────────────────────────
head ".env configuration"

ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    log "Creating .env template…"
    cat > "$ENV_FILE" << 'ENVEOF'
# Nova Agent Configuration
# Fill in your API keys. Never commit this file.

# ── Required ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-XXXXXXXXXXXXXXXXXXXXXXXX

# ── ElevenLabs TTS (optional — falls back to espeak if not set) ───────────────
ELEVENLABS_API_KEY=
# Default: Rachel (warm, feminine). Get voice IDs with: python agent.py --list-voices
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
# eleven_turbo_v2_5 (fast) or eleven_multilingual_v2 (higher quality)
ELEVENLABS_MODEL=eleven_turbo_v2_5

# Voice character (0.0 – 1.0)
VOICE_STABILITY=0.45
VOICE_SIMILARITY=0.85
VOICE_STYLE=0.35

# ── Activation ────────────────────────────────────────────────────────────────
# ptt (Enter key), keyword (say wake word), toggle, always
ACTIVATION_MODE=ptt
WAKE_WORD=nova
SLEEP_WORD=sleep nova

# ── Agent name ────────────────────────────────────────────────────────────────
AGENT_NAME=Nova

# ── VPS (optional) ────────────────────────────────────────────────────────────
VPS_HOST=
VPS_USER=ubuntu
VPS_SSH_KEY=~/.ssh/id_ed25519
TAILSCALE_IP=

# ── Misc ──────────────────────────────────────────────────────────────────────
DEBUG=false
SAFE_MODE=false
MAX_HISTORY_TURNS=30
ENVEOF
    log ".env created at $ENV_FILE — fill in your API keys."
else
    warn ".env already exists — skipping."
fi

# ── 6. Nova shortcut command ───────────────────────────────────────────────────
head "Creating 'nova' shortcut"

SHORTCUT="$PREFIX/bin/nova"
cat > "$SHORTCUT" << SHORTEOF
#!/data/data/com.termux/files/usr/bin/bash
# Nova Agent shortcut — generated by setup.sh
cd "$SCRIPT_DIR"
exec python agent.py "\$@"
SHORTEOF
chmod +x "$SHORTCUT"
log "Shortcut created: you can now run 'nova' from anywhere in Termux."

# ── 7. Termux Widget shortcut (optional) ──────────────────────────────────────
head "Termux Widget shortcut (optional)"

WIDGET_DIR="$HOME/.shortcuts"
mkdir -p "$WIDGET_DIR"
WIDGET_FILE="$WIDGET_DIR/Nova Agent"
cat > "$WIDGET_FILE" << WEOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$SCRIPT_DIR"
python agent.py --mode ptt
WEOF
chmod +x "$WIDGET_FILE"
log "Widget shortcut created: add a Termux Widget to your home screen and tap 'Nova Agent'."

# ── Done ───────────────────────────────────────────────────────────────────────
head "Setup complete"
echo
log "Next steps:"
echo "  1. Edit $ENV_FILE — add your ANTHROPIC_API_KEY (and ELEVENLABS_API_KEY)"
echo "  2. Run: nova --check          (verify everything is working)"
echo "  3. Run: nova                  (PTT mode — press Enter to talk)"
echo "  4. Run: nova --mode keyword   (always listening for 'nova')"
echo "  5. Run: nova --text           (text-only, no mic needed)"
echo
echo -e "${CYAN}Usage examples:${NC}"
echo "  nova                     # push-to-talk"
echo "  nova --mode keyword      # voice-activated"
echo "  nova --mode toggle       # Enter to start/stop"
echo "  nova --text              # text chat"
echo "  nova --list-voices       # browse ElevenLabs voices"
echo "  nova --check             # dependency check"
echo
