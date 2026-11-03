"""Launch the distributed EXE from a clean folder without a Python installation on PATH."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    report_destination = args.report.resolve()
    if os.name != "nt":
        parser.error("Run this check on Windows, where the executable will be used.")

    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("PYTHON")}
    system_root = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join([str(system_root / "System32"), str(system_root)])

    # Copy only the EXE: no adjacent config, developer DLLs, or certificate can
    # make this check pass accidentally. A space in the path also tests quoting.
    with tempfile.TemporaryDirectory(prefix="nfse executable check ") as directory:
        clean_dir = Path(directory)
        clean_exe = clean_dir / executable.name
        shutil.copy2(executable, clean_exe)
        report_path = clean_dir / "self-test.json"
        subprocess.run([str(clean_exe), "--self-test", str(report_path)],
                       cwd=clean_dir, env=env, timeout=60, check=True)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (not report.get("ok") or not report.get("frozen")
                or not {"pkcs12_to_pem", "tkinter_window"} <= set(report.get("checks", []))):
            raise RuntimeError(f"The packaged application did not pass its self-test: {report}")
        report_destination.parent.mkdir(parents=True, exist_ok=True)
        report_destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
