import os
import base64
import gzip
import logging
import datetime
import tempfile
import time
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Callable, Iterable, Optional
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import requests

from .config import Config

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

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session: Optional[requests.Session] = None

    def arquivo_nsu(self, cnpj: Optional[str] = None) -> str:
        """Keep the production checkpoint compatible and isolate test data."""
        cnpj = self.config.normalizar_cnpj(cnpj if cnpj is not None else self.config.cnpj)
        self.config.api_base_url  # Reject unknown environments before accessing state.
        suffix = "_producao_restrita" if self.config.ambiente == "producao_restrita" else ""
        return f"ultimo_nsu_{cnpj}{suffix}.txt"

    def ler_ultimo_nsu(self, cnpj: Optional[str] = None) -> int:
        """Return the last stored NSU for ``cnpj`` (defaults to config)."""
        fname = self.arquivo_nsu(cnpj)
        if os.path.exists(fname):
            with open(fname, "r", encoding="utf-8") as f:
                try:
                    value = int(f.read().strip())
                    if 1 <= value <= 2**63:
                        return value
                except Exception:
                    pass
        return 1

    def salvar_ultimo_nsu(self, nsu: int, cnpj: Optional[str] = None) -> None:
        """Persist ``nsu`` for ``cnpj`` (defaults to config)."""
        if not 1 <= nsu <= 2**63:
            raise ValueError("O próximo NSU deve estar entre 1 e 9223372036854775808.")
        fname = self.arquivo_nsu(cnpj)
        with open(fname + ".tmp", "w", encoding="utf-8") as f:
            f.write(str(nsu))
        os.replace(fname + ".tmp", fname)

    @staticmethod
    def extrair_ano_mes(xml_bytes: bytes) -> tuple[str, str]:
        """Return the year and month from ``dhEmi`` or ``dhEvento``."""
        now = datetime.datetime.now()
        try:
            root = ET.fromstring(xml_bytes)
            el = None
            for tag in ("dhEmi", "dhEvento", "DataEmissao"):
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
            pfx_path = self.config.cert_path
        if pfx_password is None:
            pfx_password = self.config.cert_pass
        data = Path(pfx_path).read_bytes()
        priv_key, cert, add_certs = load_key_and_certificates(
            data, pfx_password.encode(), None
        )
        if priv_key is None or cert is None:
            raise ValueError("O arquivo PFX deve conter o certificado e sua chave privada.")
        tmp = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        pem_path = tmp.name
        tmp.close()
        try:
            with open(pem_path, "wb") as f:
                f.write(priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
                f.write(cert.public_bytes(Encoding.PEM))
                if add_certs:
                    for ca in add_certs:
                        f.write(ca.public_bytes(Encoding.PEM))
            yield pem_path
        finally:
            os.remove(pem_path)

    def erro_api(self, resp, resposta: dict, url: str) -> RuntimeError:
        """Preserve the full server response, including Codigo and Descricao."""
        detalhes = []
        for mensagem in resposta.get("Erros") or []:
            if isinstance(mensagem, dict):
                detalhes.append(" - ".join(str(mensagem[k]) for k in
                                          ("Codigo", "Descricao", "Complemento")
                                          if mensagem.get(k)))
        texto = resp.text or json.dumps(resposta, ensure_ascii=False)
        mensagem = f"HTTP {resp.status_code} ao consultar GET {url}"
        if detalhes:
            mensagem += "\n" + "\n".join(detalhes)
        else:
            mensagem += "\nA API não informou Codigo/Descricao no campo Erros."
        mensagem += f"\nResposta completa da API: {texto}"
        self.logger.error(mensagem)
        return RuntimeError(mensagem)

    @contextmanager
    def registrar_log(self, path: str) -> Iterable[None]:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        previous_level = self.logger.level
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)
        try:
            yield
        finally:
            self.logger.removeHandler(handler)
            self.logger.setLevel(previous_level)
            handler.close()

    def run(
        self,
        write: Callable[[str, bool], None] = lambda msg, log=True: None,
        running: Callable[[], bool] = lambda: True,
    ) -> None:
        """Download NFS-e documents until ``running`` returns ``False``."""
        cfg = self.config
        cfg.validar()
        callback = write

        def write(msg: str, log: bool = True) -> None:
            if log:
                self.logger.info(msg)
            callback(msg, log=False)

        cert_path = cfg.cert_path
        cert_pass = cfg.cert_pass
        cnpj = cfg.normalizar_cnpj(cfg.cnpj)
        output_dir = cfg.output_dir
        log_dir = cfg.log_dir
        file_prefix = cfg.file_prefix
        delay_seconds = int(cfg.delay_seconds)
        timeout = int(cfg.timeout)

        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        base_url = f"{cfg.api_base_url}/DFe"
        log_name = os.path.join(log_dir, f"log_nfse_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt")
        write(f"Log registrado em: {log_name}", log=False)

        total_baixados = 0

        with self.registrar_log(log_name), self.pfx_to_pem(cert_path, cert_pass) as pem_cert:
            write(f"Consultando NFS-e para CNPJ {cnpj}; ambiente: {cfg.ambiente}.", log=True)
            nsu = self.ler_ultimo_nsu(cnpj)
            self.session = requests.Session()
            sess = self.session
            sess.cert = pem_cert
            sess.verify = True
            sess.headers.update({"Accept": "application/json"})

            try:
                while running():
                    query_nsu = max(0, nsu - 1)
                    url = f"{base_url}/{query_nsu}"
                    params = {"cnpjConsulta": cnpj, "lote": "true"}
                    request_url = f"{url}?{urlencode(params)}"
                    write(
                        f"Consultando NSU {nsu} (consulta {query_nsu}) para CNPJ {cnpj}...",
                        log=True,
                    )
                    try:
                        resp = sess.get(url, params=params, timeout=timeout)
                    except requests.exceptions.RequestException as e:
                        self.logger.error("Erro de conexão: %s", e)
                        raise RuntimeError(f"Erro de conexão com a API: {e}") from e
                    if resp.status_code == 204:
                        write("Nenhuma nota encontrada. Fim da consulta.", log=True)
                        self.salvar_ultimo_nsu(nsu, cnpj)
                        break
                    try:
                        resposta = resp.json()
                    except ValueError:
                        raise self.erro_api(resp, {}, request_url) from None
                    if not isinstance(resposta, dict):
                        raise self.erro_api(resp, {}, request_url)
                    codigos = {e.get("Codigo") for e in resposta.get("Erros") or []
                               if isinstance(e, dict)}
                    status = resposta.get("StatusProcessamento")
                    if (resp.status_code == 404
                            and status == "NENHUM_DOCUMENTO_LOCALIZADO"
                            and codigos and codigos <= {"E2220", "E2230"}):
                        write("Nenhum documento a partir do NSU informado. Fim da consulta.", log=True)
                        self.salvar_ultimo_nsu(nsu, cnpj)
                        break
                    if resp.status_code != 200 or resposta.get("Erros"):
                        raise self.erro_api(resp, resposta, request_url)
                    if resp.status_code == 200:
                        documentos = resposta.get("LoteDFe") or []
                        if status == "NENHUM_DOCUMENTO_LOCALIZADO" and not documentos:
                            write("Nenhum documento a partir do NSU informado. Fim da consulta.", log=True)
                            self.salvar_ultimo_nsu(nsu, cnpj)
                            break
                        if status == "DOCUMENTOS_LOCALIZADOS" and documentos:
                            for alerta in resposta.get("Alertas") or []:
                                write(f"Alerta da API: {alerta}", log=True)
                            if resposta.get("TipoConsulta"):
                                write(f"Tipo de autorização: {resposta['TipoConsulta']}", log=True)
                            documentos = sorted(documentos, key=lambda d: int(d.get("NSU", 0)))
                            nsu_inicial = nsu
                            stop_loop = False
                            for nfse in documentos:
                                if not running():
                                    stop_loop = True
                                    break
                                nsu_item = int(nfse["NSU"])
                                chave = nfse["ChaveAcesso"]
                                if nsu_item < nsu:
                                    continue
                                arquivo_xml = nfse["ArquivoXml"]
                                xml_gzip = base64.b64decode(arquivo_xml)
                                xml_bytes = gzip.decompress(xml_gzip)
                                ano, mes = self.extrair_ano_mes(xml_bytes)
                                tipo = nfse.get("TipoDocumento", "NFSE")
                                # Events share the NFS-e access key; never overwrite the invoice.
                                sufixo = "" if tipo == "NFSE" else f"_documento_{nsu_item}"
                                filename = os.path.join(
                                    output_dir, f"{file_prefix}_{ano}-{mes}_{chave}{sufixo}.xml"
                                )
                                write(f"NSU {nsu_item}", log=True)
                                existed = os.path.exists(filename)
                                with open(filename + ".tmp", "wb") as fxml:
                                    fxml.write(xml_bytes)
                                os.replace(filename + ".tmp", filename)
                                action = "substituído" if existed else "salvo"
                                write(
                                    f"XML Baixado e {action}: {filename}",
                                    log=True,
                                )
                                total_baixados += 1
                                self.salvar_ultimo_nsu(nsu_item + 1, cnpj)
                                nsu = nsu_item + 1
                            if stop_loop or not running():
                                break
                            if nsu == nsu_inicial:
                                raise RuntimeError("A API retornou um lote sem avanço de NSU; consulta interrompida.")
                        else:
                            raise self.erro_api(resp, resposta, request_url)
                        write(f"Aguardando {delay_seconds} segundos para o próximo lote...", log=True)
                        for _ in range(delay_seconds):
                            if not running():
                                break
                            time.sleep(1)
            finally:
                sess.close()
                self.session = None

            write(f"Processo concluído. Total baixados: {total_baixados}", log=True)

    def close(self) -> None:
        """Close the internal requests session if it exists."""
        if self.session is not None:
            try:
                self.session.close()
            finally:
                self.session = None


