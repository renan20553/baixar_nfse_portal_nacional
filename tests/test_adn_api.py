"""Offline integration regressions using real requests, with only the network mocked.

Run with: python -m unittest discover -s tests -p test_adn_api.py -v
"""
import base64
from contextlib import contextmanager
from dataclasses import asdict
import datetime
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from nfse.config import Config
from nfse.downloader import NFSeDownloader
import download_nfse


CNPJ = "11222333000181"
FILIAL = "11222333000262"
CHAVE = "1" * 50


def documento(nsu=388, tipo="NFSE", xml=None):
    if xml is None:
        xml = b"<NFSe><dhEmi>2026-11-03T12:00:00-03:00</dhEmi></NFSe>"
    return {"NSU": nsu, "ChaveAcesso": CHAVE, "TipoDocumento": tipo,
            "ArquivoXml": base64.b64encode(gzip.compress(xml)).decode()}


def lote(*docs):
    return {"TipoConsulta": "CnpjBase", "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS",
            "LoteDFe": list(docs), "Alertas": [], "Erros": []}


def sem_documentos(code="E2220"):
    return {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
            "Erros": [{"Codigo": code, "Descricao": "Nenhum documento localizado."}]}


class OfflineAdapter(requests.adapters.BaseAdapter):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False

    def send(self, request, **options):
        self.requests.append((request, options))
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        status, data = item
        response = requests.Response()
        response.status_code = status
        response._content = data if isinstance(data, bytes) else json.dumps(data).encode()
        response.encoding = "utf-8"
        response.url = request.url
        response.request = request
        return response

    def close(self):
        self.closed = True


class ADNTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        previous = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)
        self.cfg = Config(cert_path="matriz.pfx", cert_pass="secret-not-logged", cnpj=CNPJ,
                          output_dir="xml", log_dir="logs", delay_seconds=0)
        self.downloader = NFSeDownloader(self.cfg)
        self.messages = []

    def run_api(self, responses, write=None, running=lambda: True):
        self.adapter = OfflineAdapter(responses)
        session = requests.Session()
        session.mount("https://", self.adapter)
        session.mount("http://", self.adapter)

        @contextmanager
        def certificate(*args):
            yield "matriz-transmissao.pem"

        def callback(message, log=True):
            self.messages.append(message)
            if write:
                write(message)

        with patch("nfse.downloader.requests.Session", return_value=session), \
                patch.object(self.downloader, "pfx_to_pem", certificate):
            self.downloader.run(write=callback, running=running)

    def checkpoint(self, value=388):
        self.downloader.salvar_ultimo_nsu(value)

    def test_request_matches_distribution_contract_and_resumes_at_387(self):
        self.checkpoint()
        self.run_api([(200, lote(documento())), (404, sem_documentos())])
        first, options = self.adapter.requests[0]
        self.assertEqual(first.method, "GET")
        self.assertEqual(urlsplit(first.url).path, "/contribuintes/DFe/387")
        self.assertEqual(parse_qs(urlsplit(first.url).query),
                         {"cnpjConsulta": [CNPJ], "lote": ["true"]})
        self.assertEqual(first.headers["Accept"], "application/json")
        self.assertIsNone(first.body)
        # requests may resolve True to the environment's configured CA bundle.
        self.assertTrue(options["verify"])
        self.assertEqual(options["cert"], "matriz-transmissao.pem")
        self.assertEqual(options["timeout"], 30)
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 389)
        self.assertTrue(self.adapter.requests[1][0].url.split("?")[0].endswith("/388"))
        self.assertTrue(self.adapter.closed)
        self.assertIsNone(self.downloader.session)

    def test_same_matrix_certificate_can_be_selected_for_two_establishments(self):
        for cnpj in (CNPJ, FILIAL):
            self.cfg.cnpj = cnpj
            self.run_api([(200, lote(documento(1))), (404, sem_documentos())])
            req, options = self.adapter.requests[0]
            self.assertEqual(parse_qs(urlsplit(req.url).query)["cnpjConsulta"], [cnpj])
            self.assertEqual(options["cert"], "matriz-transmissao.pem")
            self.assertEqual(self.downloader.ler_ultimo_nsu(), 2)
        self.assertTrue(Path(f"ultimo_nsu_{CNPJ}.txt").exists())
        self.assertTrue(Path(f"ultimo_nsu_{FILIAL}.txt").exists())

    def test_environments_use_distinct_hosts_and_checkpoints(self):
        self.checkpoint()
        self.cfg.ambiente = "producao_restrita"
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 1)
        self.run_api([(404, sem_documentos())])
        req = self.adapter.requests[0][0]
        self.assertEqual(urlsplit(req.url).hostname, "adn.producaorestrita.nfse.gov.br")
        self.assertEqual(urlsplit(req.url).path, "/contribuintes/DFe/0")
        self.assertEqual(Path(f"ultimo_nsu_{CNPJ}_producao_restrita.txt").read_text(), "1")
        self.cfg.ambiente = "producao"
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 388)

    def test_actual_400_with_empty_errors_is_failure_and_retains_cursor(self):
        # Same response structure and metadata supplied in the user's production log.
        payload = {"TipoConsulta": "InscricaoCertificado", "StatusProcessamento": "REJEICAO",
                   "LoteDFe": [], "Alertas": [], "Erros": [], "TipoAmbiente": "PRODUCAO",
                   "VersaoAplicativo": "1.0.0.0",
                   "DataHoraProcessamento": "2026-11-03T15:19:23.7352548-03:00"}
        self.checkpoint()
        with self.assertRaisesRegex(RuntimeError, "HTTP 400") as caught:
            self.run_api([(400, payload)])
        self.assertIn("não informou Codigo/Descricao", str(caught.exception))
        self.assertIn("cnpjConsulta=", str(caught.exception))
        self.assertIn(json.dumps(payload), str(caught.exception))
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 388)
        self.assertFalse(any("Processo concluído" in x for x in self.messages))
        log = next(Path("logs").glob("*.txt")).read_text()
        self.assertIn(json.dumps(payload), log)
        self.assertNotIn(self.cfg.cert_pass, log)
        self.assertTrue(self.adapter.closed)

    def test_rejection_codes_are_preserved_without_advancing_cursor(self):
        for code in ("E2210", "E2211", "E2212", "E2213", "E2214",
                     "E2243", "E2244", "E2245", "E2246", "E2247", "E999"):
            with self.subTest(code=code):
                self.checkpoint()
                payload = {"StatusProcessamento": "REJEICAO",
                           "Erros": [{"Codigo": code, "Descricao": "Motivo do servidor",
                                      "Complemento": "Detalhe preservado"}]}
                with self.assertRaisesRegex(RuntimeError, code) as caught:
                    self.run_api([(400, payload)])
                self.assertIn("Motivo do servidor", str(caught.exception))
                self.assertIn("Detalhe preservado", str(caught.exception))
                self.assertEqual(self.downloader.ler_ultimo_nsu(), 388)

    def test_only_expected_404_codes_end_the_distribution_normally(self):
        for code in ("E2220", "E2230"):
            with self.subTest(code=code):
                self.run_api([(404, sem_documentos(code))])
                self.assertEqual(self.downloader.ler_ultimo_nsu(), 1)
        with self.assertRaisesRegex(RuntimeError, "E2241"):
            self.run_api([(404, sem_documentos("E2241"))])

    def test_non_json_errors_and_unknown_404_are_not_treated_as_empty(self):
        self.checkpoint()
        for status in (200, 400, 404, 503):
            with self.subTest(status=status):
                with self.assertRaisesRegex(RuntimeError, "server-proxy-message"):
                    self.run_api([(status, b"<html>server-proxy-message</html>")])
                self.assertEqual(self.downloader.ler_ultimo_nsu(), 388)

    def test_http_200_rejection_is_still_a_failure(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 200"):
            self.run_api([(200, {"StatusProcessamento": "REJEICAO", "Erros": []})])

    def test_legacy_empty_responses_remain_supported(self):
        self.run_api([(204, b"")])
        self.run_api([(200, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
                             "LoteDFe": [], "Erros": []})])
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 1)

    def test_connection_failure_cannot_report_success(self):
        self.checkpoint()
        with self.assertRaisesRegex(RuntimeError, "Erro de conexão"):
            self.run_api([requests.exceptions.SSLError("TLS test failure")])
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 388)
        self.assertFalse(any("Processo concluído" in m for m in self.messages))
        self.assertTrue(self.adapter.closed)

    def test_invoice_and_event_with_same_access_key_have_distinct_xml_files(self):
        invoice = b"<NFSe><dhEmi>2026-11-03</dhEmi></NFSe>"
        event = b"<evento><dhEvento>2026-11-03</dhEvento></evento>"
        self.run_api([(200, lote(documento(1, xml=invoice), documento(2, "EVENTO", event))),
                      (404, sem_documentos())])
        self.assertEqual(Path(f"xml/NFS-e_2026-11_{CHAVE}.xml").read_bytes(), invoice)
        self.assertEqual(Path(f"xml/NFS-e_2026-11_{CHAVE}_documento_2.xml").read_bytes(), event)
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 3)
        self.assertFalse(list(Path("xml").glob("*.pdf")))
        self.assertTrue(all("/DFe/" in req.url for req, _ in self.adapter.requests))

    def test_unsorted_batch_and_gaps_do_not_skip_its_first_document(self):
        self.checkpoint()
        self.run_api([(200, lote(documento(390), documento(388))), (404, sem_documentos())])
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 391)
        self.assertTrue(self.adapter.requests[1][0].url.split("?")[0].endswith("/390"))
        self.assertIn("Processo concluído. Total baixados: 2", self.messages)

    def test_stop_mid_batch_keeps_next_cursor_without_rolling_back(self):
        self.checkpoint()
        stopped = [False]

        def on_write(message):
            if message.startswith("XML Baixado"):
                stopped[0] = True

        self.run_api([(200, lote(documento(388), documento(389)))],
                     write=on_write, running=lambda: not stopped[0])
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 389)
        self.assertEqual(len(self.adapter.requests), 1)

    def test_bad_xml_compression_preserves_last_successful_checkpoint(self):
        self.checkpoint()
        bad = documento(389)
        bad["ArquivoXml"] = base64.b64encode(b"not gzip").decode()
        with self.assertRaises(gzip.BadGzipFile):
            self.run_api([(200, lote(documento(388), bad))])
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 389)
        self.assertTrue(self.adapter.closed)

    def test_failed_xml_write_does_not_advance_or_overwrite_existing_invoice(self):
        self.checkpoint()
        Path("xml").mkdir()
        dest = Path(f"xml/NFS-e_2026-11_{CHAVE}.xml")
        dest.write_bytes(b"original invoice")
        with patch("nfse.downloader.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                self.run_api([(200, lote(documento()))])
        self.assertEqual(dest.read_bytes(), b"original invoice")
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 388)

    def test_formatted_cnpj_is_sent_unformatted(self):
        self.cfg.cnpj = "11.222.333/0001-81"
        self.run_api([(404, sem_documentos())])
        req = self.adapter.requests[0][0]
        self.assertEqual(parse_qs(urlsplit(req.url).query)["cnpjConsulta"], [CNPJ])
        self.assertEqual(self.downloader.arquivo_nsu(), f"ultimo_nsu_{CNPJ}.txt")

    def test_invalid_cnpj_or_environment_fails_before_certificate_or_http(self):
        for cnpj, ambiente in (("123", "producao"), (CNPJ, "unknown")):
            with self.subTest(cnpj=cnpj, ambiente=ambiente):
                self.cfg.cnpj, self.cfg.ambiente = cnpj, ambiente
                with patch("nfse.downloader.requests.Session") as session:
                    with self.assertRaises(ValueError):
                        self.downloader.run()
                    session.assert_not_called()

    def test_old_pdf_setting_is_accepted_and_removed_on_save(self):
        data = asdict(self.cfg)
        data.pop("ambiente")
        data["download_pdf"] = True
        path = Path("legacy.json")
        path.write_text(json.dumps(data))
        loaded = Config.load(str(path))
        self.assertEqual(loaded.ambiente, "producao")
        loaded.save(str(path))
        self.assertNotIn("download_pdf", json.loads(path.read_text()))

    def test_new_config_is_created_with_production_default(self):
        path = Path("config.json")
        cfg = Config.load(str(path))
        self.assertEqual(json.loads(path.read_text()), asdict(cfg))
        self.assertEqual(cfg.ambiente, "producao")

    def test_failed_auto_start_keeps_error_visible(self):
        app = download_nfse.App.__new__(download_nfse.App)
        app.downloader = Mock()
        app.downloader.run.side_effect = RuntimeError("HTTP 400")
        app.config = self.cfg
        app.config.auto_start = True
        app.user_stop = False
        app.running = True
        app.root = Mock()
        app.status_label = Mock()
        app.start_button = Mock()
        app.stop_button = Mock()
        app.logger = Mock()
        app.write = Mock()
        app.download_nfse()
        app.root.after.assert_not_called()
        app.status_label.config.assert_not_called()
        self.assertFalse(app.running)
        app.write.assert_called_once_with("Falha no download: HTTP 400", log=True)

    def test_nsu_files_are_compatible_and_negative_values_are_rejected(self):
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 1)
        self.checkpoint(99)
        self.assertEqual(NFSeDownloader(self.cfg).ler_ultimo_nsu(), 99)
        for value in (-1, 0, 2**63 + 1):
            with self.assertRaises(ValueError):
                self.checkpoint(value)
        self.assertEqual(self.downloader.ler_ultimo_nsu(), 99)

    def test_pfx_conversion_keeps_key_certificate_and_chain_and_cleans_up(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test only")])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
        data = pkcs12.serialize_key_and_certificates(
            b"test", key, cert, [cert], serialization.BestAvailableEncryption(b"test-password"))
        path = Path("test.pfx")
        path.write_bytes(data)
        with self.downloader.pfx_to_pem(str(path), "test-password") as pem:
            pem_path = Path(pem)
            content = pem_path.read_bytes()
            self.assertIn(b"BEGIN PRIVATE KEY", content)
            self.assertEqual(content.count(b"BEGIN CERTIFICATE"), 2)
            recovered = serialization.load_pem_private_key(content, password=None)
            self.assertEqual(recovered.private_numbers(), key.private_numbers())
        self.assertFalse(pem_path.exists())
        with self.assertRaisesRegex(RuntimeError, "operation failed"):
            with self.downloader.pfx_to_pem(str(path), "test-password") as pem:
                pem_path = Path(pem)
                raise RuntimeError("operation failed")
        self.assertFalse(pem_path.exists())


if __name__ == "__main__":
    unittest.main()
