import sys
from pathlib import Path

# Ensure repository root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from license_text import LICENSE_TEXT, EXPECTED_LICENSE_TEXT


def test_license_text_embedded() -> None:
    assert LICENSE_TEXT == EXPECTED_LICENSE_TEXT
