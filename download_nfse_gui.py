import json
import logging
import os
import sys
import tempfile
import threading
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from nfse.downloader import NFSeDownloader

try:
    from version import __version__  # type: ignore
except Exception:
    __version__ = "0.0.0"

from license_text import LICENSE_TEXT

CONFIG_FILE = "config.json"


class App:
    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.root.title(f"Download NFS-e Portal Nacional v{__version__}")
        self.text = ScrolledText(root, width=100, height=30, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=True)
        self.status_label = tk.Label(root, text="Pronto", anchor='w')
        self.status_label.pack(fill=tk.X)
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None
        self.user_stop = False
        self.downloader = NFSeDownloader(config)

        self.start_button = tk.Button(root, text="Iniciar Download", command=self.start)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_button = tk.Button(root, text="Parar", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.settings_button = tk.Button(root, text="Configurações", command=self.open_settings)
        self.settings_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.about_button = tk.Button(root, text="Sobre", command=self.show_about)
        self.about_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.settings_win = None  # referencia para a janela de configuração
        self.about_win = None  # referencia para a janela Sobre

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
        add_entry(5, "file_prefix", "Prefixo Arquivo")
        add_entry(6, "delay_seconds", "Delay (s)")
        add_entry(7, "timeout", "Timeout (s)")

        auto_start_var = tk.BooleanVar(value=bool(self.config.get("auto_start", False)))
        tk.Checkbutton(win, text="Auto iniciar", variable=auto_start_var).grid(row=8, column=1, sticky="w", padx=5, pady=2)

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

        tk.Button(win, text="Salvar", command=save).grid(row=9, column=0, columnspan=3, pady=5)

    def show_about(self) -> None:
        """Display information about the application with the license text."""
        if self.about_win is not None:
            try:
                exists = self.about_win.winfo_exists()
            except Exception:
                exists = False
            if exists:
                self.about_win.lift()
                self.about_win.focus_force()
                return

        win = tk.Toplevel(self.root)
        self.about_win = win
        win.title("Sobre")

        def on_close() -> None:
            self.about_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

        text = ScrolledText(win, width=80, height=25, wrap=tk.WORD)
        about_text = (
            f"Download NFS-e Portal Nacional v{__version__}\n"
            "Autor: Renan R. Santos\n\n"
            f"{LICENSE_TEXT}"
        )
        text.insert(tk.END, about_text)
        text.config(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Button(win, text="Fechar", command=on_close).pack(pady=5)

    def download_nfse(self):
        try:
            self.downloader.run(write=self.write, running=lambda: self.running)
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
    cfg.setdefault("file_prefix", "NFS-e")
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
