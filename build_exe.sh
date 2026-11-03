#!/usr/bin/env bash
# Build the standalone executable for download_nfse.py using PyInstaller.
# On Windows, use Python 3.12 x64 and install requirements-build.txt first.

set -e

python -m PyInstaller --clean --onefile --noconsole --noupx \
  --version-file version_file.txt \
  download_nfse.py

python scripts/check_windows_executable.py dist/download_nfse.exe --report dist/self-test.json

# Copy license so the About dialog can read it when packaged
cp LICENSE dist/

# Copy configuration file next to the executable
cp config.json dist/

echo "Executable validated in dist/. Configure the path to your PFX/P12 certificate in config.json."
