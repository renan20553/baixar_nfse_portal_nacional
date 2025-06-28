import sys
from pathlib import Path

# Ensure repository root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from license_text import LICENSE_TEXT


def test_license_text_embedded() -> None:
    license_file = Path(__file__).resolve().parents[1] / "LICENSE"
    assert LICENSE_TEXT == license_file.read_text(encoding="utf-8").strip()
