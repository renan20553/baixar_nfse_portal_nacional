import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import download_nfse_gui
from dataclasses import asdict
from nfse.config import Config


def test_ler_config_creates_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(download_nfse_gui, "CONFIG_FILE", str(cfg_file))
    cfg = Config.load(str(cfg_file))
    assert cfg_file.exists()
    assert asdict(cfg) == asdict(Config())
    # file content should match returned config
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data == asdict(cfg)
