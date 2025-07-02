#!/usr/bin/env bash
# Build the standalone executable for download_nfse_gui.py using PyInstaller.
# Install PyInstaller with `pip install pyinstaller` if necessary.

set -e

pyinstaller --onefile --noconsole --noupx \
  --version-file version_file.txt \
  download_nfse_gui.py

# Copy license so the About dialog can read it when packaged
cp LICENSE dist/

# Copy configuration file next to the executable
cp config.json dist/

echo "Executable created in dist/ without console window. Copy your certificate (.pfx or .pem) to the same folder."
