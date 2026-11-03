from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from typing import ClassVar


@dataclass
class Config:
    cert_path: str = "caminho/para/certificado.pfx"
    cert_pass: str = "sua_senha"
    cnpj: str = "00000000000000"
    output_dir: str = "./xml"
    log_dir: str = "logs"
    file_prefix: str = "NFS-e"
    ambiente: str = "producao"
    delay_seconds: int = 60
    auto_start: bool = False
    timeout: int = 30

    REQUIRED_FIELDS = ["cert_path", "cert_pass", "cnpj", "output_dir", "log_dir"]
    API_URLS: ClassVar[dict[str, str]] = {
        "producao": "https://adn.nfse.gov.br/contribuintes",
        "producao_restrita": "https://adn.producaorestrita.nfse.gov.br/contribuintes",
    }

    @property
    def api_base_url(self) -> str:
        try:
            return self.API_URLS[self.ambiente]
        except KeyError:
            raise ValueError("Ambiente inválido: use producao ou producao_restrita.") from None

    @staticmethod
    def normalizar_cnpj(cnpj: str) -> str:
        # Preserve letters for the alphanumeric CNPJ supported since August 2026.
        value = re.sub(r"[.\s/\-]", "", str(cnpj)).upper()
        if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", value):
            raise ValueError("Informe o CNPJ completo da empresa consultada (14 caracteres).")
        return value

    def validar(self) -> None:
        self.api_base_url
        self.normalizar_cnpj(self.cnpj)
        if int(self.timeout) <= 0 or int(self.delay_seconds) < 0:
            raise ValueError("Timeout deve ser positivo e o intervalo não pode ser negativo.")

    @classmethod
    def load(cls, path: str) -> "Config":
        """Load configuration from ``path`` or create it with defaults."""
        created = False
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
            created = True
        # The DANFSe v1 API was disabled on 2026-08-03. Accept old configs.
        data.pop("download_pdf", None)
        cfg_data = asdict(cls())
        cfg_data.update(data)
        cfg = cls(**cfg_data)
        missing = [k for k in cls.REQUIRED_FIELDS if not getattr(cfg, k)]
        if missing and not created:
            raise ValueError(
                "Campos obrigatórios ausentes no config.json: " + ", ".join(missing)
            )
        if created:
            cfg.save(path)
        return cfg

    def save(self, path: str) -> None:
        """Persist configuration to ``path`` as JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
