#!/usr/bin/env bash
#
# Build the macOS desktop app into dist/AegisTrans.app and package it into dist/AegisTrans-macos.zip.
#
# Usage:
#   ./build.sh [--skip-assets]
#

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SKIP_ASSETS=false

for arg in "$@"; do
    case "$arg" in
        --skip-assets)
            SKIP_ASSETS=true
            ;;
        --clean)
            echo "==> Cleaning build and dist artifacts..."
            rm -rf "$ROOT/build" "$ROOT/dist"
            echo "==> Clean complete."
            exit 0
            ;;
        -h|--help)
            echo "Usage: ./build.sh [--skip-assets] [--clean]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

if [[ ! -x "$PYTHON" ]]; then
    echo "==> Creating virtual environment at .venv..."
    python3 -m venv "$ROOT/.venv"
fi

echo "==> Installing app and packaging dependencies"
"$PYTHON" -m pip install -r "$ROOT/requirements-app.txt"

if [[ "$SKIP_ASSETS" != "true" ]]; then
    echo "==> Fetching layout model and font"
    "$PYTHON" "$ROOT/scripts/fetch_assets.py"
fi

# Ensure macOS icon is present and in sync with icon.png
ICNS="$ROOT/app/assets/icon.icns"
PNG="$ROOT/app/assets/icon.png"
if [[ -f "$PNG" && (! -f "$ICNS" || "$PNG" -nt "$ICNS") ]]; then
    echo "==> Generating icon.icns from icon.png..."
    ICONSET_DIR="$ROOT/app/assets/icon.iconset"
    mkdir -p "$ICONSET_DIR"
    sips -z 16 16     "$PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1
    sips -z 32 32     "$PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1
    sips -z 32 32     "$PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1
    sips -z 64 64     "$PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1
    sips -z 128 128   "$PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1
    sips -z 256 256   "$PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1
    sips -z 256 256   "$PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1
    sips -z 512 512   "$PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1
    sips -z 512 512   "$PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1
    sips -z 1024 1024 "$PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null 2>&1
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS"
    rm -rf "$ICONSET_DIR"
fi

# Kill any running instance of AegisTrans from dist to avoid locking
pkill -f "dist/AegisTrans.app" 2>/dev/null || true

echo "==> Running PyInstaller"
"$PYTHON" -m PyInstaller --noconfirm --clean "$ROOT/app.spec"

OUTPUT_APP="$ROOT/dist/AegisTrans.app"
if [[ ! -d "$OUTPUT_APP" ]]; then
    echo "Error: PyInstaller did not produce $OUTPUT_APP" >&2
    exit 1
fi

# Check required files inside .app bundle
REQUIRED_FILES=(
    "Contents/MacOS/AegisTrans"
    "Contents/Info.plist"
)
if [[ "$SKIP_ASSETS" != "true" || -f "$ROOT/app/assets/doclayout.onnx" ]]; then
    REQUIRED_FILES+=(
        "Contents/Resources/app/assets/doclayout.onnx"
        "Contents/Resources/app/assets/GoNotoKurrent-Regular.ttf"
    )
fi
for f in "${REQUIRED_FILES[@]}"; do
    if [[ ! -e "$OUTPUT_APP/$f" ]]; then
        echo "Error: Missing required file in bundle: $f" >&2
        exit 1
    fi
done

# Clean up intermediate unbundled folder and PyInstaller build caches
rm -rf "$ROOT/dist/AegisTrans" "$ROOT/build"

ARCHIVE="$ROOT/dist/AegisTrans-macos.zip"
echo "==> Zipping to $ARCHIVE"
rm -f "$ARCHIVE"
(cd "$ROOT/dist" && zip -r -y -q "$ARCHIVE" "AegisTrans.app")

APP_SIZE=$(du -sh "$OUTPUT_APP" | awk '{print $1}')
ZIP_SIZE=$(du -sh "$ARCHIVE" | awk '{print $1}')

echo "==> Done. App bundle: $APP_SIZE, Archive: $ZIP_SIZE"
echo "Note: If distributing outside the Mac App Store without Apple Developer ID, tell users to run:"
echo "  xattr -cr /Applications/AegisTrans.app"
