import requests


def download_nfse(urls):
    """Download files from given URLs and save them locally."""
    sess = None
    try:
        sess = requests.Session()
        for url in urls:
            resp = sess.get(url)
            resp.raise_for_status()
            filename = url.split('/')[-1] or 'downloaded_file'
            with open(filename, 'wb') as f:
                f.write(resp.content)
    finally:
        if sess is not None:
            sess.close()
