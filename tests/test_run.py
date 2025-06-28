import base64
import gzip
import os
import sys
import types
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub cryptography modules
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

from nfse.downloader import NFSeDownloader


class DummyResp:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data or {}
        self.text = ""

    def json(self):
        return self._data


class DummySession:
    def __init__(self):
        self.calls = 0

    def get(self, url, timeout=0):
        self.calls += 1
        if self.calls == 1:
            xml = gzip.compress(b"<xml/>")
            doc = base64.b64encode(xml).decode()
            data = {
                "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS",
                "LoteDFe": [{"NSU": "1", "ChaveAcesso": "k1", "ArquivoXml": doc}],
            }
            return DummyResp(200, data)
        return DummyResp(204, {})

    def close(self):
        pass


def test_run_updates_nsu(tmp_path, monkeypatch):
    session = DummySession()
    req_mod = types.ModuleType("requests")
    req_mod.Session = lambda: session
    req_mod.exceptions = types.SimpleNamespace(RequestException=Exception)
    monkeypatch.setitem(sys.modules, "requests", req_mod)
    import nfse.downloader as dl_mod
    monkeypatch.setattr(dl_mod, "requests", req_mod)

    cfg = {
        "cert_path": "dummy",
        "cert_pass": "x",
        "cnpj": "123",
        "output_dir": str(tmp_path),
        "log_dir": str(tmp_path),
        "delay_seconds": 0,
        "download_pdf": False,
    }

    dl = NFSeDownloader(cfg)

    @contextmanager
    def dummy_pfx(self, *a, **k):
        yield str(tmp_path / "cert.pem")

    monkeypatch.setattr(NFSeDownloader, "pfx_to_pem", dummy_pfx)

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        dl.run(write=lambda *a, **k: None, running=lambda: session.calls < 1)
    finally:
        os.chdir(cwd)

    nsu_file = tmp_path / "ultimo_nsu_123.txt"
    assert nsu_file.exists()
    assert nsu_file.read_text() == "2"
