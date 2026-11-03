# Correção do executável Windows — 03/11/2026

O executável da compilação 121 falhava ao iniciar, com `DLL load failed while importing _rust`. O log do GitHub Actions identifica a dependência ausente:

```text
WARNING: Library not found: could not resolve 'python3t.dll', dependency of '...cryptography..._rust.pyd'.
```

Essa compilação usou CPython 3.15.2, cryptography 50.0.2 e PyInstaller 6.22.3. O workflow selecionava `python-version: 3.x`, permitindo trocar automaticamente a versão principal/secundária do interpretador. O wheel utilizado foi `cryptography-50.0.2-cp315-abi3.abi3t-win_amd64.whl`.

No Python 3.15, extensões `abi3.abi3t` no Windows usam `python3t.dll`. A localização dessa DLL difere entre instalações e variantes do Python. O empacotador não resolveu essa dependência na compilação examinada. A falha ocorre na importação do módulo, antes da interface e de qualquer requisição à NFS-e; não é uma rejeição HTTP 400 nem depende do certificado do usuário.

## Alterações

- Fixado CPython 3.12 x64 no workflow, usando o wheel compatível com essa versão, sem a ABI nova do Python 3.15.
- Fixadas as versões de requests, cryptography, PyInstaller e seus hooks em `requirements-build.txt`, mantendo cryptography 50.0.2.
- Build no runner `windows-2022`, correspondente a um dos sistemas informados pelo usuário. Windows 11 também precisa de validação final na máquina do usuário.
- Instalação somente de pacotes binários e `pip check`, seguida dos testes de regressão.
- PyInstaller com `--clean` para não reutilizar análise de outra combinação de pacotes.
- Teste real do `.exe` antes do upload e da criação de release. Ele roda uma cópia isolada do executável, sem configuração e sem DLLs adjacentes, com o Python de desenvolvimento fora do `PATH`.

O autoteste gera um certificado temporário local, cria um PFX, executa a conversão PFX → PEM usada pelo programa e abre/fecha uma janela Tkinter. Não acessa a rede nem usa certificado ou senha do usuário. Falha, timeout, relatório ausente ou resultado inválido impedem a publicação do artefato. O resultado é salvo em `self-test.json` junto ao executável.

O sucesso da compilação, isoladamente, não comprova a inicialização do programa. O novo teste cobre essa diferença; a resolução do HTTP 400 continua dependendo da consulta com certificado autorizado na API.

## Referências

- [Log da compilação 121](https://github.com/renan20553/baixar_nfse_portal_nacional/actions/runs/41700832752)
- [Código do PyInstaller: resolução das bibliotecas Python no Windows](https://github.com/pyinstaller/pyinstaller/blob/develop/PyInstaller/building/build_main.py) — descreve a localização de `python3t.dll` e a ABI introduzida no Python 3.15.
- [CPython: carregamento de extensões no Windows](https://github.com/python/cpython/blob/main/Python/dynload_win.c)
- [Instalação e plataformas do cryptography 50.0.2](https://cryptography.io/en/50.0.2/installation/)
