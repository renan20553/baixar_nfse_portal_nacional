from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfse.pdf_downloader import NFSePDFDownloader


def test_base_url_constant():
    assert (
        NFSePDFDownloader.BASE_URL
        == "https://sefin.nfse.gov.br/sefinnacional/danfse"
    )


class DummyResp:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content
        self.text = ""


class DummySession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout=0):
        self.calls.append(url)
        return DummyResp(200, b"pdfdata")


def test_baixar(tmp_path: Path):
    session = DummySession()
    dl = NFSePDFDownloader(session, timeout=1)
    dest = tmp_path / "nota.pdf"
    chave = "123"
    assert dl.baixar(chave, str(dest))
    assert dest.read_bytes() == b"pdfdata"
    assert session.calls[0] == f"{NFSePDFDownloader.BASE_URL}/{chave}"
