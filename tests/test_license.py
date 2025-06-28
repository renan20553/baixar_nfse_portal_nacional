import importlib
import os
import sys
from pathlib import Path
import types

import pytest

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

import download_nfse_gui


def reload_gui(monkeypatch, args=None, env=None):
    args = args or []
    env = env or {}
    monkeypatch.setattr(sys, "argv", ["prog"] + args)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(download_nfse_gui)


def test_license_text_read(monkeypatch) -> None:
    mod = reload_gui(monkeypatch)
    license_file = Path(__file__).resolve().parents[1] / "LICENSE"
    assert mod.LICENSE_FILE == license_file
    assert mod.LICENSE_TEXT == license_file.read_text(encoding="utf-8").strip()


def test_license_arg(monkeypatch, tmp_path) -> None:
    custom = tmp_path / "my_license"
    custom.write_text("ARG")
    mod = reload_gui(monkeypatch, args=[f"--license={custom}"])
    assert mod.LICENSE_FILE == custom.resolve()
    assert mod.LICENSE_TEXT == "ARG"


def test_license_env(monkeypatch, tmp_path) -> None:
    custom = tmp_path / "env_license"
    custom.write_text("ENV")
    mod = reload_gui(monkeypatch, env={"LICENSE_PATH": str(custom)})
    assert mod.LICENSE_FILE == custom.resolve()
    assert mod.LICENSE_TEXT == "ENV"
