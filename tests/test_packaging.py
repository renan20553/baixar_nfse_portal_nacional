import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfse.selftest import run_self_test


class PackagingSelfTestTests(unittest.TestCase):
    def test_pfx_conversion_and_report_do_not_need_user_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "self-test.json"
            window = Mock()
            with patch("nfse.selftest.tk.Tk", return_value=window):
                result = run_self_test(str(report_path), "test-build")
            report = json.loads(report_path.read_text())
            self.assertEqual(result, 0)
            self.assertTrue(report["ok"])
            self.assertEqual(report["app_version"], "test-build")
            self.assertEqual(report["checks"], ["pkcs12_to_pem", "tkinter_window"])
            self.assertEqual(list(Path(directory).iterdir()), [report_path])
            window.withdraw.assert_called_once()
            window.destroy.assert_called_once()

    def test_tk_runtime_failure_is_reported_as_failed_self_test(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with patch("nfse.selftest.tk.Tk", side_effect=RuntimeError("missing Tcl DLL")):
                result = run_self_test(str(path), "test-build")
            report = json.loads(path.read_text())
            self.assertEqual(result, 1)
            self.assertFalse(report["ok"])
            self.assertIn("missing Tcl DLL", report["error"])
            self.assertNotIn("tkinter_window", report["checks"])

    def test_cryptographic_failure_cannot_pass_self_test(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with patch("nfse.selftest.rsa.generate_private_key", side_effect=RuntimeError("native failure")), \
                    patch("nfse.selftest.tk.Tk") as window:
                result = run_self_test(str(path), "test-build")
            report = json.loads(path.read_text())
            self.assertEqual(result, 1)
            self.assertFalse(report["ok"])
            self.assertEqual(report["checks"], [])
            window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
