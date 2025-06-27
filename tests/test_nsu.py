import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path

import pytest

from baixar_nfse_portal_nacional.nsu import ler_ultimo_nsu, salvar_ultimo_nsu


def test_salvar_e_ler_nsu(tmp_path: Path) -> None:
    file_path = tmp_path / "ultimo_nsu.txt"
    salvar_ultimo_nsu("123", file_path)
    assert file_path.read_text() == "123"
    assert ler_ultimo_nsu(file_path) == "123"


def test_ler_nsu_inexistente(tmp_path: Path) -> None:
    file_path = tmp_path / "ausente.txt"
    with pytest.raises(FileNotFoundError):
        ler_ultimo_nsu(file_path)
