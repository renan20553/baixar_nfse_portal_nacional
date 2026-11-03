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

from dataclasses import asdict

from nfse.downloader import NFSeDownloader
from nfse.config import Config

try:
    from version import __version__  # type: ignore
except Exception:
    __version__ = "0.0.0"

from license_text import LICENSE_TEXT

CONFIG_FILE = "config.json"

# Valores padrao para criacao automatica do arquivo de configuracao
DEFAULT_CONFIG = asdict(Config())


def dialog_initial_options(path: str, *, file: bool = False) -> dict:
    """Start a picker at the current field, falling back to an existing parent."""
    current = os.path.abspath(os.path.expanduser(path.strip())) if path.strip() else os.getcwd()
    options = {}
    if file and not os.path.isdir(current):
        options["initialfile"] = os.path.basename(current)
        current = os.path.dirname(current)
    while not os.path.isdir(current):
        parent = os.path.dirname(current)
        if parent == current:
            current = os.getcwd()
            break
        current = parent
    options["initialdir"] = current
    return options


class App:
    def __init__(self, root, config: Config):
        self.root = root
        self.config = config
        self.root.title(f"Download NFS-e Portal Nacional v{__version__}")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.text = ScrolledText(root, width=100, height=30, font=("Consolas", 10))
        self.text.grid(row=0, column=0, sticky="nsew")

        self.bottom_frame = tk.Frame(root)
        self.bottom_frame.grid(row=1, column=0, sticky="ew")

        self.button_frame = tk.Frame(self.bottom_frame)
        self.button_frame.pack(side=tk.TOP)

        self.status_label = tk.Label(self.bottom_frame, text="Pronto", anchor="w")
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None
        self.user_stop = False
        self.downloader = NFSeDownloader(config)

        self.start_button = tk.Button(self.button_frame, text="Iniciar Download", command=self.start)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.stop_button = tk.Button(self.button_frame, text="Parar", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.settings_button = tk.Button(self.button_frame, text="Configurações", command=self.open_settings)
        self.settings_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.about_button = tk.Button(self.button_frame, text="Sobre", command=self.show_about)
        self.about_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.nsu_button = tk.Button(self.button_frame, text="Editar NSU", command=self.open_nsu_editor)
        self.nsu_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.settings_win = None  # referencia para a janela de configuração
        self.about_win = None  # referencia para a janela Sobre

        if self.config.auto_start:
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
        self.downloader.close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
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
            var = tk.StringVar(value=str(getattr(self.config, key)))
            entry = tk.Entry(win, textvariable=var, width=50)
            entry.grid(row=row, column=1, padx=5, pady=2)
            vars_[key] = var
            if browse == "file":
                def choose():
                    path = filedialog.askopenfilename(
                        parent=win, **dialog_initial_options(var.get(), file=True))
                    if path:
                        var.set(path)
                tk.Button(win, text="...", command=choose).grid(row=row, column=2, padx=2, pady=2)
            elif browse == "dir":
                def choose():
                    path = filedialog.askdirectory(
                        parent=win, **dialog_initial_options(var.get()))
                    if path:
                        var.set(path)
                tk.Button(win, text="...", command=choose).grid(row=row, column=2, padx=2, pady=2)

        add_entry(0, "cert_path", "Certificado", browse="file")
        add_entry(1, "cert_pass", "Senha")
        add_entry(2, "cnpj", "CNPJ consultado (matriz/filial)")
        add_entry(3, "output_dir", "Diretório XML", browse="dir")
        add_entry(4, "log_dir", "Diretório Log", browse="dir")
        add_entry(5, "file_prefix", "Prefixo Arquivo")
        add_entry(6, "delay_seconds", "Delay (s)")
        add_entry(7, "timeout", "Timeout (s)")

        ambientes = {"Produção": "producao", "Produção restrita (testes)": "producao_restrita"}
        ambiente_label = next((label for label, value in ambientes.items()
                               if value == self.config.ambiente), "Produção")
        ambiente_var = tk.StringVar(value=ambiente_label)
        tk.Label(win, text="Ambiente").grid(row=8, column=0, sticky="w", padx=5, pady=2)
        tk.OptionMenu(win, ambiente_var, *ambientes).grid(row=8, column=1, sticky="w", padx=5, pady=2)

        auto_start_var = tk.BooleanVar(value=bool(self.config.auto_start))
        tk.Checkbutton(win, text="Auto iniciar", variable=auto_start_var).grid(row=9, column=1, sticky="w", padx=5, pady=2)
        tk.Label(win, text="Pode usar o certificado da matriz para filial da mesma raiz de CNPJ.").grid(
            row=10, column=0, columnspan=3, padx=5, pady=2)

        def save():
            new_data = asdict(self.config)
            for k, v in vars_.items():
                if k in ("delay_seconds", "timeout"):
                    try:
                        new_data[k] = int(v.get())
                    except ValueError:
                        messagebox.showerror("Erro", f"Valor inválido para {k}")
                        return
                else:
                    new_data[k] = v.get()
            new_data["auto_start"] = auto_start_var.get()
            new_data["ambiente"] = ambientes[ambiente_var.get()]
            new_config = Config(**new_data)
            try:
                new_config.validar()
                new_config.cnpj = new_config.normalizar_cnpj(new_config.cnpj)
            except ValueError as e:
                messagebox.showerror("Erro de configuração", str(e))
                return
            self.config = new_config
            # Update the downloader instance so new settings take effect
            self.downloader.config = self.config
            self.config.save(CONFIG_FILE)
            messagebox.showinfo("Configurações", "Configurações salvas com sucesso!")
            on_close()

        tk.Button(win, text="Salvar", command=save).grid(row=11, column=0, columnspan=3, pady=5)

    def open_nsu_editor(self):
        win = tk.Toplevel(self.root)
        win.title("Editar NSU")

        try:
            nsu_file = self.downloader.arquivo_nsu()
            next_nsu = self.downloader.ler_ultimo_nsu()
        except ValueError as e:
            win.destroy()
            messagebox.showerror("Erro de configuração", str(e))
            return
        file_var = tk.StringVar(value=nsu_file)
        nsu_var = tk.StringVar(value=str(next_nsu))

        tk.Label(win, text="Arquivo NSU").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Entry(win, textvariable=file_var, width=40).grid(row=0, column=1, padx=5, pady=2)

        def choose_file():
            path = filedialog.askopenfilename(
                parent=win, filetypes=[("TXT", "*.txt"), ("All", "*.*")],
                **dialog_initial_options(file_var.get(), file=True))
            if path:
                file_var.set(path)
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            nsu_var.set(str(int(f.read().strip())))
                    except Exception:
                        pass

        tk.Button(win, text="...", command=choose_file).grid(row=0, column=2, padx=2, pady=2)

        tk.Label(win, text="Próximo NSU").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Entry(win, textvariable=nsu_var, width=20).grid(row=1, column=1, padx=5, pady=2)

        def save():
            try:
                nsu = int(nsu_var.get())
                self.downloader.salvar_ultimo_nsu(nsu, self.config.cnpj)
            except ValueError:
                messagebox.showerror("Erro", "NSU inválido")
                return
            # also save to chosen path if different
            path = file_var.get()
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(str(nsu))
            except Exception:
                pass
            messagebox.showinfo("NSU", "NSU salvo com sucesso!")
            win.destroy()

        tk.Button(win, text="Salvar", command=save).grid(row=2, column=0, columnspan=3, pady=5)

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
        completed = False
        try:
            self.downloader.run(write=self.write, running=lambda: self.running)
            completed = True
            self.status_label.config(text="Processo concluído")
        except Exception as e:
            self.logger.error("Falha no download: %s", e)
            self.write(f"Falha no download: {e}", log=True)
        finally:
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            if completed and self.config.auto_start and not self.user_stop:
                self.root.after(1000, self.root.destroy)

REQUIRED_FIELDS = ["cert_path", "cert_pass", "cnpj", "output_dir", "log_dir"]


def ler_config() -> Config:
    return Config.load(CONFIG_FILE)


def salvar_config(cfg: Config | dict) -> None:
    if isinstance(cfg, Config):
        cfg.save(CONFIG_FILE)
    else:
        Config(**cfg).save(CONFIG_FILE)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from nfse.selftest import run_self_test

        report_path = sys.argv[2] if len(sys.argv) > 2 else "self-test.json"
        sys.exit(run_self_test(report_path, __version__))

    try:
        cfg = Config.load(CONFIG_FILE)
    except Exception as e:
        tk.Tk().withdraw()
        messagebox.showerror("Erro de configuração", str(e))
        sys.exit(1)

    root = tk.Tk()
    app = App(root, cfg)
    root.mainloop()
