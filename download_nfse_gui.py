import requests
import json
import os
import base64
import gzip
import time
import datetime
import logging
import sys
from pathlib import Path
from contextlib import contextmanager
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
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
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None
        self.user_stop = False

        self.start_button = tk.Button(root, text="Iniciar Download", command=self.start)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_button = tk.Button(root, text="Parar", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.settings_button = tk.Button(root, text="Configurações", command=self.open_settings)
        self.settings_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.settings_win = None  # referencia para a janela de configuração

        if self.config.get("auto_start", False):
            self.root.after(500, self.start)  # pequeno delay para interface carregar antes de iniciar

    def write(self, msg, log=True):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        msg_fmt = f"[{now}] {msg}\n"
        self.text.insert(tk.END, msg_fmt)
        self.text.see(tk.END)
        self.status_label.config(text=msg)
        if log:
            self.logger.info(msg)

    def start(self):
        if self.running:
            return
        self.user_stop = False
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
        self.user_stop = True
        self.status_label.config(text="Encerrando... aguarde")
        self.write("Parando processo... aguarde.", log=True)
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def open_settings(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("Configurações")

        def on_close():
            self.settings_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

        vars_ = {}

        def add_entry(row, key, label, browse=None):
            tk.Label(win, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar(value=str(self.config.get(key, "")))
            entry = tk.Entry(win, textvariable=var, width=50)
            entry.grid(row=row, column=1, padx=5, pady=2)
            vars_[key] = var
            if browse == "file":
                def choose():
                    path = filedialog.askopenfilename(parent=win)
                    if path:
                        var.set(path)
                tk.Button(win, text="...", command=choose).grid(row=row, column=2, padx=2, pady=2)
            elif browse == "dir":
                def choose():
                    path = filedialog.askdirectory(parent=win)
                    if path:
                        var.set(path)
                tk.Button(win, text="...", command=choose).grid(row=row, column=2, padx=2, pady=2)

        add_entry(0, "cert_path", "Certificado", browse="file")
        add_entry(1, "cert_pass", "Senha")
        add_entry(2, "cnpj", "CNPJ")
        add_entry(3, "output_dir", "Diretório XML", browse="dir")
        add_entry(4, "log_dir", "Diretório Log", browse="dir")
        add_entry(5, "delay_seconds", "Delay (s)")
        add_entry(6, "timeout", "Timeout (s)")

        auto_start_var = tk.BooleanVar(value=bool(self.config.get("auto_start", False)))
        tk.Checkbutton(win, text="Auto iniciar", variable=auto_start_var).grid(row=7, column=1, sticky="w", padx=5, pady=2)

        def save():
            new_cfg = self.config.copy()
            for k, v in vars_.items():
                if k in ("delay_seconds", "timeout"):
                    try:
                        new_cfg[k] = int(v.get())
                    except ValueError:
                        messagebox.showerror("Erro", f"Valor inválido para {k}")
                        return
                else:
                    new_cfg[k] = v.get()
            new_cfg["auto_start"] = auto_start_var.get()
            self.config = new_cfg
            salvar_config(new_cfg)
            messagebox.showinfo("Configurações", "Configurações salvas com sucesso!")
            on_close()

        tk.Button(win, text="Salvar", command=save).grid(row=8, column=0, columnspan=3, pady=5)

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
            logging.basicConfig(filename=log_name, level=logging.INFO,
                                format="%(asctime)s %(levelname)s: %(message)s")
            self.write(f"Log registrado em: {log_name}", log=False)
            self.write(f"Consultando NFS-e para CNPJ {CNPJ}.", log=True)

            nsus_baixados = set()
            total_baixados = 0

            with pfx_to_pem(CERT_PATH, CERT_PASS) as pem_cert:
                with requests.Session() as sess:
                    sess.cert = pem_cert
                    sess.verify = True

                    nsu = ler_ultimo_nsu(CNPJ)
                    while self.running:
                        url = f"{BASE_URL}/{nsu:020d}?cnpj={CNPJ}"
                        self.write(f"Consultando NSU {nsu} para CNPJ {CNPJ}...", log=True)
                        try:
                            resp = sess.get(url, timeout=self.config.get("timeout", 30))
                        except Exception as e:
                            self.logger.error("Erro de conexão: %s", e)
                            self.write(f"Erro de conexão: {e}", log=True)
                            salvar_ultimo_nsu(CNPJ, nsu)
                            break
                        if resp.status_code == 200:
                            resposta = resp.json()
                            documentos = resposta.get("LoteDFe", [])
                            if resposta.get("StatusProcessamento") == "DOCUMENTOS_LOCALIZADOS" and documentos:
                                documentos = sorted(documentos, key=lambda d: int(d.get("NSU", 0)))
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
                                self.logger.error("Resposta inesperada ou nenhum documento localizado.")
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
                            self.logger.error("Erro: %s %s", resp.status_code, resp.text)
                            self.write(f"Erro: {resp.status_code} {resp.text}", log=True)
                            salvar_ultimo_nsu(CNPJ, nsu)
                            break

            self.write(f"Processo concluído. Total baixados: {total_baixados}", log=True)
            self.status_label.config(text="Processo concluído")
        except Exception as e:
            self.logger.error("Erro inesperado: %s", e)
            self.write(f"Erro inesperado: {e}", log=True)
        finally:
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            if self.config.get("auto_start") and not self.user_stop:
                self.root.after(1000, self.root.destroy)

REQUIRED_FIELDS = ["cert_path", "cert_pass", "cnpj", "output_dir", "log_dir"]

def ler_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Arquivo de configuração '{CONFIG_FILE}' não encontrado.")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    missing = [k for k in REQUIRED_FIELDS if not cfg.get(k)]
    if missing:
        raise ValueError("Campos obrigatórios ausentes no config.json: " + ", ".join(missing))

    cfg.setdefault("delay_seconds", 60)
    cfg.setdefault("timeout", 30)
    cfg.setdefault("auto_start", False)
    return cfg

def salvar_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    try:
        cfg = ler_config()
    except Exception as e:
        tk.Tk().withdraw()
        messagebox.showerror("Erro de configuração", str(e))
        sys.exit(1)

    root = tk.Tk()
    app = App(root, cfg)
    root.mainloop()
