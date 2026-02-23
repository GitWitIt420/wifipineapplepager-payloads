#!/bin/bash
# install.sh - Install all payloads from this repository to the WiFi Pineapple Pager
#
# Usage:
#   ./install.sh [TARGET_DIR]
#
# TARGET_DIR defaults to /mmc/root/payloads (standard pager payload location).
# Alert payloads are installed as DISABLED.<name> by default so they don't fire
# unintentionally. Enable them via the pager UI or rename to remove the prefix.

TARGET_DIR="${1:-/mmc/root/payloads}"
LIBRARY_DIR="$(cd "$(dirname "$0")/library" && pwd)"

COUNT_NEW=0
COUNT_SKIPPED=0

install_payload() {
    local src_path="$1"       # directory containing payload.sh
    local rel_path="$2"       # path relative to library root
    local dir_name
    dir_name="$(basename "$src_path")"

    # Determine the target path
    local target_path="$TARGET_DIR/$rel_path"

    # Alert payloads: check whether a disabled copy already exists; if neither
    # enabled nor disabled copy exists, install as disabled by default.
    local in_alerts=false
    if [[ "$rel_path" == alerts/* ]]; then
        in_alerts=true
    fi

    local disabled_path
    disabled_path="$(dirname "$target_path")/DISABLED.$dir_name"

    if $in_alerts; then
        # If enabled or disabled copy already exists, skip
        if [ -d "$target_path" ] || [ -d "$disabled_path" ]; then
            COUNT_SKIPPED=$((COUNT_SKIPPED + 1))
            return
        fi
        # Install as disabled
        target_path="$disabled_path"
    else
        if [ -d "$target_path" ]; then
            COUNT_SKIPPED=$((COUNT_SKIPPED + 1))
            return
        fi
    fi

    mkdir -p "$(dirname "$target_path")"
    cp -r "$src_path" "$target_path"
    COUNT_NEW=$((COUNT_NEW + 1))
    echo "  [INSTALLED] $rel_path"
}

main() {
    if [ ! -d "$LIBRARY_DIR" ]; then
        echo "ERROR: library directory not found at $LIBRARY_DIR" >&2
        exit 1
    fi

    echo "Installing payloads from: $LIBRARY_DIR"
    echo "Destination:              $TARGET_DIR"
    echo ""

    mkdir -p "$TARGET_DIR"

    # Find every payload.sh and install its containing directory
    while IFS= read -r pfile; do
        local src_path
        src_path="$(dirname "$pfile")"
        local rel_path="${src_path#$LIBRARY_DIR/}"
        install_payload "$src_path" "$rel_path"
    done < <(find "$LIBRARY_DIR" -name "payload.sh" | sort)

    echo ""
    echo "Done: $COUNT_NEW installed, $COUNT_SKIPPED already present (skipped)."
    echo ""
    if [ "$COUNT_NEW" -gt 0 ] && [[ "$TARGET_DIR" == /mmc/* ]]; then
        echo "Note: Alert payloads were installed as DISABLED.<name>."
        echo "      Enable them in the pager UI or rename to remove the DISABLED. prefix."
    fi
}

main
