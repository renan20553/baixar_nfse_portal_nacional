import json
from pathlib import Path
import requests

CONFIG_PATH = Path('config.json')
DEFAULT_TIMEOUT = 30

def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            try:
                data = json.load(f)
                return data.get('timeout', DEFAULT_TIMEOUT)
            except json.JSONDecodeError:
                return DEFAULT_TIMEOUT
    return DEFAULT_TIMEOUT

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
    timeout = load_config()
    resp = sess.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content
