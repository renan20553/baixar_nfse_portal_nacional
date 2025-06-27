import json
from pathlib import Path
import requests

CONFIG_PATH = Path('config.json')
DEFAULT_TIMEOUT = 30

def load_config() -> dict:
    """Load configuration from ``config.json``.

    Returns a dictionary with at least the ``timeout`` key. If the file does
    not exist or is invalid, a dictionary with the default timeout is
    returned.
    """
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    if not isinstance(data, dict):
        data = {}

    data.setdefault("timeout", DEFAULT_TIMEOUT)
    return data

def download_nfse(sess: requests.Session, url: str) -> bytes:
    """Download NFSe file using the provided session and URL.

    Parameters
    ----------
    sess : requests.Session
        The session object to use for the request.
    url : str
        The NFSe download URL.

    Returns
    -------
    bytes
        The response content.
    """
    config = load_config()
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    resp = sess.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content
