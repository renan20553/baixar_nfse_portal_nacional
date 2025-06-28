class NFSePDFDownloader:
    """Simple helper to download PDF documents from the national portal."""

    BASE_URL = "https://sefin.nfse.gov.br/sefinnacional//danfse"

    def __init__(self, session, timeout: int = 30):
        self.session = session
        self.timeout = timeout

    def baixar(self, chave: str, dest_path: str) -> bool:
        """Download ``chave`` to ``dest_path``. Returns ``True`` on success."""
        url = f"{self.BASE_URL}/{chave}"
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code == 200:
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return True
        return False
