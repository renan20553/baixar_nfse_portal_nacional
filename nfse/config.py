from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict


@dataclass
class Config:
    cert_path: str = "caminho/para/certificado.pfx"
    cert_pass: str = "sua_senha"
    cnpj: str = "00000000000000"
    output_dir: str = "./xml"
    log_dir: str = "logs"
    file_prefix: str = "NFS-e"
    download_pdf: bool = False
    delay_seconds: int = 60
    auto_start: bool = False
    timeout: int = 30

    REQUIRED_FIELDS = ["cert_path", "cert_pass", "cnpj", "output_dir", "log_dir"]

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
