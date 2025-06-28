import sys
from pathlib import Path
import types

# Ensure repository root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub external dependencies used by download_nfse_gui
sys.modules.setdefault("requests", types.ModuleType("requests"))

crypto = types.ModuleType("cryptography")
hazmat = types.ModuleType("cryptography.hazmat")
primitives = types.ModuleType("cryptography.hazmat.primitives")
serialization = types.ModuleType("cryptography.hazmat.primitives.serialization")
pkcs12 = types.ModuleType("cryptography.hazmat.primitives.serialization.pkcs12")
serialization.Encoding = object()
serialization.PrivateFormat = object()
serialization.NoEncryption = object()
pkcs12.load_key_and_certificates = lambda data, pwd, backend: (None, None, None)
crypto.hazmat = hazmat
hazmat.primitives = primitives
primitives.serialization = serialization
serialization.pkcs12 = pkcs12
sys.modules["cryptography"] = crypto
sys.modules["cryptography.hazmat"] = hazmat
sys.modules["cryptography.hazmat.primitives"] = primitives
sys.modules["cryptography.hazmat.primitives.serialization"] = serialization
sys.modules["cryptography.hazmat.primitives.serialization.pkcs12"] = pkcs12

from download_nfse_gui import LICENSE_TEXT

def test_license_text_read() -> None:
    license_file = Path(__file__).resolve().parents[1] / "LICENSE"
    assert LICENSE_TEXT == license_file.read_text(encoding="utf-8").strip()
