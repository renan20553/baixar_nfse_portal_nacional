import sys
import types
from pathlib import Path

import pytest

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


class DummyWin:
    def __init__(self, root=None):
        self.exists = True
        self.protocols = {}
    def title(self, *args, **kwargs):
        pass
    def lift(self):
        pass
    def focus_force(self):
        pass
    def winfo_exists(self):
        return self.exists
    def destroy(self):
        self.exists = False
    def protocol(self, name, func):
        self.protocols[name] = func

class DummyButton:
    def __init__(self, master, text="", command=None):
        self.command = command
    def pack(self, *args, **kwargs):
        pass

class DummyScrolledText:
    def __init__(self, master, **kwargs):
        pass
    def insert(self, *args, **kwargs):
        pass
    def config(self, *args, **kwargs):
        pass
    def pack(self, *args, **kwargs):
        pass

class DummyTkModule(types.SimpleNamespace):
    pass


def setup_dummy_tk(monkeypatch):
    dummy_tk = DummyTkModule(
        Toplevel=lambda root=None: DummyWin(),
        WORD="word",
        Button=DummyButton,
        END="end",
        DISABLED="disabled",
        BOTH="both",
    )
    monkeypatch.setattr(download_nfse_gui, "tk", dummy_tk)
    monkeypatch.setattr(download_nfse_gui, "ScrolledText", DummyScrolledText)
    return dummy_tk


def test_show_about_open_close(monkeypatch):
    setup_dummy_tk(monkeypatch)
    App = download_nfse_gui.App
    app = App.__new__(App)
    app.root = None
    app.config = {}
    app.about_win = None

    app.show_about()
    win = app.about_win
    assert win is not None
    assert win.winfo_exists()

    # simulate close via WM_DELETE_WINDOW
    win.protocols["WM_DELETE_WINDOW"]()
    assert app.about_win is None
    assert not win.winfo_exists()


