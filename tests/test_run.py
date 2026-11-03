import base64
import gzip
import os
import sys
import types
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfse.downloader import NFSeDownloader
from nfse.config import Config


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
        self.urls = []
        self.params = []
        self.headers = {}

    def get(self, url, timeout=0, params=None):
        self.calls += 1
        self.urls.append(url)
        self.params.append(params)
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

    cfg = Config(
        cert_path="dummy",
        cert_pass="x",
        cnpj="11222333000181",
        output_dir=str(tmp_path),
        log_dir=str(tmp_path),
        delay_seconds=0,
    )

    dl = NFSeDownloader(cfg)

    @contextmanager
    def dummy_pfx(self, *a, **k):
        yield str(tmp_path / "cert.pem")

    monkeypatch.setattr(NFSeDownloader, "pfx_to_pem", dummy_pfx)

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        dl.run(write=lambda *a, **k: None, running=lambda: session.calls < 2)
    finally:
        os.chdir(cwd)

    assert session.urls
    first_url = session.urls[0]
    assert first_url.endswith("/DFe/0")
    assert session.params[0] == {"cnpjConsulta": cfg.cnpj, "lote": "true"}

    nsu_file = tmp_path / "ultimo_nsu_11222333000181.txt"
    assert nsu_file.exists()
    assert nsu_file.read_text() == "2"
