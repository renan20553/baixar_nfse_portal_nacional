import os
import sys
from pathlib import Path
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub external dependencies used by download_nfse
sys.modules.setdefault("requests", types.ModuleType("requests"))

crypto = types.ModuleType("cryptography")
hazmat = types.ModuleType("cryptography.hazmat")
primitives = types.ModuleType("cryptography.hazmat.primitives")
serialization = types.ModuleType("cryptography.hazmat.primitives.serialization")
pkcs12 = types.ModuleType(
    "cryptography.hazmat.primitives.serialization.pkcs12"
)
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
sys.modules[
    "cryptography.hazmat.primitives.serialization.pkcs12"
] = pkcs12

from nfse.downloader import NFSeDownloader
from nfse.config import Config


def test_salvar_e_ler_nsu(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        dl = NFSeDownloader(Config(cnpj="12345678901234"))
        dl.salvar_ultimo_nsu(42)
        file_path = tmp_path / "ultimo_nsu_12345678901234.txt"
        assert file_path.read_text() == "42"
        assert dl.ler_ultimo_nsu() == 42
    finally:
        os.chdir(cwd)


def test_ler_nsu_padrao(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        dl = NFSeDownloader(Config(cnpj="99999999999999"))
        assert dl.ler_ultimo_nsu() == 1
    finally:
        os.chdir(cwd)


def test_salvar_nsu_persiste_novo_obj(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        cfg = Config(cnpj="00000000000001")
        dl = NFSeDownloader(cfg)
        dl.salvar_ultimo_nsu(99)
        dl2 = NFSeDownloader(cfg)
        assert dl2.ler_ultimo_nsu() == 99
    finally:
        os.chdir(cwd)


def test_extrair_ano_mes() -> None:
    xml = "<root><DataEmissao>2024-05-10T10:00:00</DataEmissao></root>"
    ano, mes = NFSeDownloader.extrair_ano_mes(xml.encode())
    assert ano == "2024"
    assert mes == "05"


def test_extrair_ano_mes_dhemi() -> None:
    xml = "<root><dhEmi>2025-06-25T10:49:08-03:00</dhEmi></root>"
    ano, mes = NFSeDownloader.extrair_ano_mes(xml.encode())
    assert ano == "2025"
    assert mes == "06"


def test_extrair_ano_mes_dhevento() -> None:
    xml = "<root><dhEvento>2026-12-31T23:59:59-03:00</dhEvento></root>"
    ano, mes = NFSeDownloader.extrair_ano_mes(xml.encode())
    assert ano == "2026"
    assert mes == "12"
