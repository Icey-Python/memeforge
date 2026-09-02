#!/usr/bin/env bash
# Fetch a free gameplay loop into server/assets/gameplay/<id>.mp4.
# Usage: ./fetch-gameplay.sh minecraft-parkour <url-to-mp4>
set -euo pipefail

ID="${1:-}"
URL="${2:-}"

if [[ -z "$ID" || -z "$URL" ]]; then
  echo "Usage: $0 <gameplay-id> <mp4-url>"
  echo "  e.g. $0 minecraft-parkour https://example.com/parkour.mp4"
  exit 1
fi

DEST="$(cd "$(dirname "$0")" && pwd)/assets/gameplay/${ID}.mp4"
mkdir -p "$(dirname "$DEST")"

if command -v ffmpeg >/dev/null 2>&1; then
  # Normalize to H.264 1080x960 (bottom half of the vertical canvas), 30fps.
  ffmpeg -y -i "$URL" -vf "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,fps=30" -an -c:v libx264 -pix_fmt yuv420p "$DEST"
else
  curl -fsSL "$URL" -o "$DEST"
fi
echo "Saved gameplay loop to $DEST"
