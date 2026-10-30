#!/usr/bin/env bash
# Install SiteOne Crawler binary into ./bin (no root required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/bin"
VERSION="${SITEONE_VERSION:-2.5.1}"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) DEB_ARCH="amd64" ;;
  aarch64|arm64) DEB_ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

DEB_URL="https://dl.cloudsmith.io/public/janreges/siteone-crawler/deb/ubuntu/pool/any-version/main/s/si/siteone-crawler-static_${VERSION}-1/siteone-crawler-static_${VERSION}-1_${DEB_ARCH}.deb"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading SiteOne Crawler ${VERSION} (${DEB_ARCH})…"
curl -fsSL -o "$TMP/siteone.deb" "$DEB_URL"
mkdir -p "$TMP/extract" "$BIN_DIR"
dpkg-deb -x "$TMP/siteone.deb" "$TMP/extract"
cp "$TMP/extract/usr/bin/siteone-crawler" "$BIN_DIR/siteone-crawler"
chmod +x "$BIN_DIR/siteone-crawler"

echo "Installed: $BIN_DIR/siteone-crawler"
"$BIN_DIR/siteone-crawler" --version
echo "Optional: export SITEONE_CRAWLER_BIN=$BIN_DIR/siteone-crawler"
