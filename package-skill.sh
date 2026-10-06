#!/bin/sh
# Build dist/ping-pong-skill.zip: a single top-level ping-pong/ folder with
# SKILL.md at its root, ready to unzip into a host's skills directory.
set -eu
cd "$(dirname "$0")"
mkdir -p dist
rm -f dist/ping-pong-skill.zip
find ping-pong -name '__pycache__' -type d -exec rm -rf {} +
zip -qr dist/ping-pong-skill.zip ping-pong \
  -x '*/__pycache__/*' '*.pyc' '*.DS_Store'
echo "dist/ping-pong-skill.zip"
unzip -l dist/ping-pong-skill.zip
