import requests
import json
import os
import base64
import gzip
import time
import datetime
from pathlib import Path
from contextlib import contextmanager
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
import tempfile
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

CONFIG_FILE = "config.json"

@contextmanager
def pfx_to_pem(pfx_path, pfx_password):
    data = Path(pfx_path).read_bytes()
    priv_key, cert, add_certs = load_key_and_certificates(data, pfx_password.encode(), None)
    tmp = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    pem_path = tmp.name
    tmp.close()
    with open(pem_path, "wb") as f:
        f.write(priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        f.write(cert.public_bytes(Encoding.PEM))
        if add_certs:
            for ca in add_certs:
                f.write(ca.public_bytes(Encoding.PEM))
    try:
        yield pem_path
    finally:
        os.remove(pem_path)

def ler_ultimo_nsu(cnpj):
    fname = f"ultimo_nsu_{cnpj}.txt"
    if os.path.exists(fname):
        with open(fname, "r") as f:
            try:
                return int(f.read().strip())
            except Exception:
                pass
    return 1

def salvar_ultimo_nsu(cnpj, nsu):
    fname = f"ultimo_nsu_{cnpj}.txt"
    with open(fname, "w") as f:
        f.write(str(nsu))

class App:
    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.root.title("Download NFS-e Nacional")
        self.text = ScrolledText(root, width=100, height=30, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=True)
        self.status_label = tk.Label(root, text="Pronto", anchor='w')
        self.status_label.pack(fill=tk.X)
        self.log_file = None
        self.running = False
        self.thread = None

        self.start_button = tk.Button(root, text="Iniciar Download", command=self.start)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_button = tk.Button(root, text="Parar", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)

        if self.config.get("auto_start", False):
            self.root.after(500, self.start)  # pequeno delay para interface carregar antes de iniciar

    def write(self, msg, log=True):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        msg_fmt = f"[{now}] {msg}\n"
        self.text.insert(tk.END, msg_fmt)
        self.text.see(tk.END)
        self.status_label.config(text=msg)
        if log and self.log_file:
            self.log_file.write(msg_fmt)
            self.log_file.flush()

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.text.delete(1.0, tk.END)
        self.status_label.config(text="Iniciando...")
        self.thread = threading.Thread(target=self.download_nfse)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.status_label.config(text="Encerrando... aguarde")
        self.write("Parando processo... aguarde.", log=True)
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def download_nfse(self):
        try:
            cfg = self.config
            CERT_PATH = cfg["cert_path"]
            CERT_PASS = cfg["cert_pass"]
            CNPJ = cfg["cnpj"]
            OUTPUT_DIR = cfg["output_dir"]
            LOG_DIR = cfg["log_dir"]
            DELAY_SECONDS = int(cfg.get("delay_seconds", 60))

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            os.makedirs(LOG_DIR, exist_ok=True)
            BASE_URL = "https://adn.nfse.gov.br/contribuintes/DFe"
            log_name = os.path.join(LOG_DIR, f"log_nfse_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            self.log_file = open(log_name, "w", encoding="utf-8")
            self.write(f"Log registrado em: {log_name}", log=False)
            self.write(f"Consultando NFS-e para CNPJ {CNPJ}.", log=True)

            nsus_baixados = set()
            total_baixados = 0

            with pfx_to_pem(CERT_PATH, CERT_PASS) as pem_cert:
                sess = requests.Session()
                sess.cert = pem_cert
                sess.verify = True

                nsu = ler_ultimo_nsu(CNPJ)
                while self.running:
                    url = f"{BASE_URL}/{nsu:020d}?cnpj={CNPJ}"
                    self.write(f"Consultando NSU {nsu} para CNPJ {CNPJ}...", log=True)
                    try:
                        resp = sess.get(url)
                    except Exception as e:
                        self.write(f"Erro de conexão: {e}", log=True)
                        salvar_ultimo_nsu(CNPJ, nsu)
                        break
                    if resp.status_code == 200:
                        resposta = resp.json()
                        documentos = resposta.get("LoteDFe", [])
                        if resposta.get("StatusProcessamento") == "DOCUMENTOS_LOCALIZADOS" and documentos:
                            nsu_maior = nsu
                            for nfse in documentos:
                                nsu_item = int(nfse["NSU"])
                                chave = nfse["ChaveAcesso"]
                                if nsu_item in nsus_baixados:
                                    continue
                                nsus_baixados.add(nsu_item)
                                arquivo_xml = nfse["ArquivoXml"]
                                xml_gzip = base64.b64decode(arquivo_xml)
                                xml_bytes = gzip.decompress(xml_gzip)
                                filename = os.path.join(OUTPUT_DIR, f"NFS-e_NSU_{nsu_item}_{chave}.xml")
                                if not os.path.exists(filename):
                                    with open(filename, "wb") as fxml:
                                        fxml.write(xml_bytes)
                                    self.write(f"Baixado e salvo: {filename}", log=True)
                                    total_baixados += 1
                                nsu_maior = max(nsu_maior, nsu_item)
                            salvar_ultimo_nsu(CNPJ, nsu_maior + 1)
                            nsu = nsu_maior + 1
                        else:
                            self.write("Resposta inesperada ou nenhum documento localizado.", log=True)
                            salvar_ultimo_nsu(CNPJ, nsu)
                            break
                        self.write(f"Aguardando {DELAY_SECONDS} segundos para o próximo lote...", log=True)
                        for i in range(DELAY_SECONDS):
                            if not self.running:
                                break
                            time.sleep(1)
                    elif resp.status_code == 204:
                        self.write("Nenhuma nota encontrada. Fim da consulta.", log=True)
                        salvar_ultimo_nsu(CNPJ, nsu)
                        break
                    else:
                        self.write(f"Erro: {resp.status_code} {resp.text}", log=True)
                        salvar_ultimo_nsu(CNPJ, nsu)
                        break

            self.write(f"Processo concluído. Total baixados: {total_baixados}", log=True)
            self.status_label.config(text="Processo concluído")
        except Exception as e:
            self.write(f"Erro inesperado: {e}", log=True)
        finally:
            if self.log_file:
                self.log_file.close()
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

def ler_config():
    if not os.path.exists(CONFIG_FILE):
        raise Exception(f"Arquivo {CONFIG_FILE} não encontrado.")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    cfg = ler_config()
    root = tk.Tk()
    app = App(root, cfg)
    root.mainloop()
