"""Exercise the frozen application's native dependencies without user data or API calls."""
import datetime
import json
from pathlib import Path
import platform
import sys
import tempfile
import tkinter as tk

import cryptography
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from .config import Config
from .downloader import NFSeDownloader


def run_self_test(report_path: str, app_version: str) -> int:
    report = {
        "ok": False,
        "app_version": app_version,
        "python_version": platform.python_version(),
        "cryptography_version": cryptography.__version__,
        "platform": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "checks": [],
    }
    try:
        # Generating and reading a PFX exercises _rust.pyd and its DLLs, rather
        # than merely checking that the Python modules were collected.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NFS-e package self-test")])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=1))
                .sign(key, hashes.SHA256()))
        password = "local-self-test-only"
        pfx = pkcs12.serialize_key_and_certificates(
            b"self-test", key, cert, None,
            serialization.BestAvailableEncryption(password.encode()),
        )
        with tempfile.TemporaryDirectory(prefix="nfse-self-test-") as directory:
            path = Path(directory) / "test.pfx"
            path.write_bytes(pfx)
            downloader = NFSeDownloader(Config(cert_path=str(path), cert_pass=password))
            with downloader.pfx_to_pem() as pem:
                recovered = serialization.load_pem_private_key(Path(pem).read_bytes(), None)
                if recovered.public_key().public_numbers() != key.public_key().public_numbers():
                    raise RuntimeError("The packaged PFX-to-PEM conversion changed the key.")
            if Path(pem).exists():
                raise RuntimeError("The temporary PEM was not removed.")
        report["checks"].append("pkcs12_to_pem")

        root = tk.Tk()
        try:
            root.withdraw()
            root.update_idletasks()
        finally:
            root.destroy()
        report["checks"].append("tkinter_window")
        report["ok"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1
