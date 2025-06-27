# NFSe Portal Nacional Downloader

This project provides a simple script to download NFSe invoices from the Portal Nacional in an automated way.

## Requirements

This project requires **Python 3.10** or newer.

## Setup

Create a virtual environment (optional but recommended) and install the
dependencies from `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `requirements.txt` file lists the required packages such as `requests` and `cryptography`.

## Configuration

Create a `config.json` file in the project root with the following keys:

- `cert_path`: Path to the `.pfx` or `.pem` certificate file.
- `cert_pass`: Password for the certificate.
- `cnpj`: The company's CNPJ used to log in to the portal.
- `output_dir`: Directory where downloaded NFSe XML files will be saved.
- `delay_seconds`: Number of seconds to wait between requests.
- `auto_start`: `true` to start downloading automatically when the script launches.
- `timeout` *(optional)*: Request timeout in seconds. Defaults to `30`.

Example `config.json`:

```json
{
  "cert_path": "path/to/certificate.pfx",
  "cert_pass": "my_password",
  "cnpj": "12345678000199",
  "output_dir": "./xml",
  "delay_seconds": 2,
  "auto_start": true,
  "timeout": 30
}
```

## Running

The provided `download_nfse_gui.py` script reads this configuration. Run it with:

```bash
python3 download_nfse_gui.py
```

The script will read `config.json`, log in using the provided certificate, and download the NFSe files to the specified output directory.
