import os
import base64
import gzip
import logging
import datetime
import tempfile
import time
from pathlib import Path
from contextlib import contextmanager
from typing import Callable, Iterable, Optional
import xml.etree.ElementTree as ET

import requests

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    NoEncryption,
)
from cryptography.hazmat.primitives.serialization.pkcs12 import (
    load_key_and_certificates,
)


class NFSeDownloader:
    """Utility class to download NFS-e documents."""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def ler_ultimo_nsu(self, cnpj: Optional[str] = None) -> int:
        """Return the last stored NSU for ``cnpj`` (defaults to config)."""
        if cnpj is None:
            cnpj = self.config.get("cnpj", "")
        fname = f"ultimo_nsu_{cnpj}.txt"
        if os.path.exists(fname):
            with open(fname, "r", encoding="utf-8") as f:
                try:
                    return int(f.read().strip())
                except Exception:
                    pass
        return 1

    def salvar_ultimo_nsu(self, nsu: int, cnpj: Optional[str] = None) -> None:
        """Persist ``nsu`` for ``cnpj`` (defaults to config)."""
        if cnpj is None:
            cnpj = self.config.get("cnpj", "")
        fname = f"ultimo_nsu_{cnpj}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(str(nsu))

    @staticmethod
    def extrair_ano_mes(xml_bytes: bytes) -> tuple[str, str]:
        """Return the year and month from the XML's emission date."""
        now = datetime.datetime.now()
        try:
            root = ET.fromstring(xml_bytes)
            el = None
            for tag in ("dhEmi", "DataEmissao"):
                el = root.find(f'.//{{*}}{tag}')
                if el is not None and el.text:
                    break
            if el is not None and el.text:
                txt = el.text.strip()
                try:
                    dt = datetime.datetime.fromisoformat(txt.replace("Z", ""))
                    return str(dt.year), f"{dt.month:02d}"
                except Exception:
                    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                        try:
                            dt = datetime.datetime.strptime(txt[:10], fmt)
                            return str(dt.year), f"{dt.month:02d}"
                        except Exception:
                            continue
        except Exception:
            pass
        return str(now.year), f"{now.month:02d}"

    @contextmanager
    def pfx_to_pem(
        self,
        pfx_path: Optional[str] = None,
        pfx_password: Optional[str] = None,
    ) -> Iterable[str]:
        """Convert ``pfx_path`` to a temporary PEM file."""
        if pfx_path is None:
            pfx_path = self.config.get("cert_path")
        if pfx_password is None:
            pfx_password = self.config.get("cert_pass")
        data = Path(pfx_path).read_bytes()
        priv_key, cert, add_certs = load_key_and_certificates(
            data, pfx_password.encode(), None
        )
        tmp = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        pem_path = tmp.name
        tmp.close()
        with open(pem_path, "wb") as f:
            f.write(priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            f.write(cert.public_bytes(Encoding.PEM))
            if add_certs:
                for ca in add_certs:
                    f.write(ca.public_bytes(Encoding.PEM))
        try:
            yield pem_path
        finally:
            os.remove(pem_path)

    def run(
        self,
        write: Callable[[str, bool], None] = lambda msg, log=True: None,
        running: Callable[[], bool] = lambda: True,
    ) -> None:
        """Download NFS-e documents until ``running`` returns ``False``."""
        cfg = self.config
        cert_path = cfg["cert_path"]
        cert_pass = cfg["cert_pass"]
        cnpj = cfg["cnpj"]
        output_dir = cfg["output_dir"]
        log_dir = cfg["log_dir"]
        file_prefix = cfg.get("file_prefix", "NFS-e")
        delay_seconds = int(cfg.get("delay_seconds", 60))
        timeout = int(cfg.get("timeout", 30))

        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        base_url = "https://adn.nfse.gov.br/contribuintes/DFe"
        log_name = os.path.join(log_dir, f"log_nfse_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        logging.basicConfig(
            filename=log_name,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s: %(message)s",
        )
        write(f"Log registrado em: {log_name}", log=False)
        write(f"Consultando NFS-e para CNPJ {cnpj}.", log=True)

        nsus_baixados = set()
        total_baixados = 0

        with self.pfx_to_pem(cert_path, cert_pass) as pem_cert:
            with requests.Session() as sess:
                sess.cert = pem_cert
                sess.verify = True

                nsu = self.ler_ultimo_nsu(cnpj)
                while running():
                    url = f"{base_url}/{nsu:020d}?cnpj={cnpj}"
                    write(f"Consultando NSU {nsu} para CNPJ {cnpj}...", log=True)
                    try:
                        resp = sess.get(url, timeout=timeout)
                    except Exception as e:
                        self.logger.error("Erro de conexão: %s", e)
                        write(f"Erro de conexão: {e}", log=True)
                        self.salvar_ultimo_nsu(nsu, cnpj)
                        break
                    if resp.status_code == 200:
                        resposta = resp.json()
                        documentos = resposta.get("LoteDFe", [])
                        if resposta.get("StatusProcessamento") == "DOCUMENTOS_LOCALIZADOS" and documentos:
                            documentos = sorted(documentos, key=lambda d: int(d.get("NSU", 0)))
                            nsu_maior = nsu
                            for nfse in documentos:
                                nsu_item = int(nfse["NSU"])
                                chave = nfse["ChaveAcesso"]
                                if nsu_item in nsus_baixados:
                                    continue
                                nsus_baixados.add(nsu_item)
                                arquivo_xml = nfse["ArquivoXml"]
                                xml_gzip = base64.b64decode(arquivo_xml)
                                xml_bytes = gzip.decompress(xml_gzip)
                                ano, mes = self.extrair_ano_mes(xml_bytes)
                                filename = os.path.join(
                                    output_dir, f"{file_prefix}_{ano}-{mes}_{chave}.xml"
                                )
                                if not os.path.exists(filename):
                                    with open(filename, "wb") as fxml:
                                        fxml.write(xml_bytes)
                                    write(f"Baixado e salvo: {filename}", log=True)
                                    total_baixados += 1
                                nsu_maior = max(nsu_maior, nsu_item)
                            self.salvar_ultimo_nsu(nsu_maior + 1, cnpj)
                            nsu = nsu_maior + 1
                        else:
                            self.logger.error("Resposta inesperada ou nenhum documento localizado.")
                            write("Resposta inesperada ou nenhum documento localizado.", log=True)
                            self.salvar_ultimo_nsu(nsu, cnpj)
                            break
                        write(f"Aguardando {delay_seconds} segundos para o próximo lote...", log=True)
                        for _ in range(delay_seconds):
                            if not running():
                                break
                            time.sleep(1)
                    elif resp.status_code == 204:
                        write("Nenhuma nota encontrada. Fim da consulta.", log=True)
                        self.salvar_ultimo_nsu(nsu, cnpj)
                        break
                    else:
                        self.logger.error("Erro: %s %s", resp.status_code, resp.text)
                        write(f"Erro: {resp.status_code} {resp.text}", log=True)
                        self.salvar_ultimo_nsu(nsu, cnpj)
                        break

        write(f"Processo concluído. Total baixados: {total_baixados}", log=True)


