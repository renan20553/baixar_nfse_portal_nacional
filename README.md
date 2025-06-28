# Downloader de NFS-e do Portal Nacional

Este projeto fornece um script simples para baixar Notas Fiscais de Serviço eletrônicas (NFS-e) do Portal Nacional de forma automatizada.

## Requisitos

Este projeto requer **Python 3.10** ou superior.

## Configuração do ambiente (Linux/macOS)

Crie um ambiente virtual (opcional, mas recomendado) e instale as dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

O arquivo `requirements.txt` lista pacotes necessários como `requests` e `cryptography`.

## Configuração do ambiente no Windows

Abra o Prompt de Comando ou o PowerShell e execute:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Arquivo `config.json`

Crie um arquivo `config.json` na raiz do projeto com as seguintes chaves:

- `cert_path`: caminho para o certificado `.pfx` ou `.pem`.
- `cert_pass`: senha do certificado.
- `cnpj`: CNPJ utilizado para login no portal.
- `output_dir`: diretório onde os XML baixados serão salvos.
- `log_dir`: diretório onde os arquivos de log serão criados.
- `file_prefix`: texto prefixo para os nomes dos arquivos XML.
- `delay_seconds`: intervalo em segundos entre as consultas ao portal.
- `auto_start`: `true` para iniciar o download automaticamente ao abrir o programa.
- `timeout`: tempo limite das requisições em segundos (padrão `30`).

**Importante:** o certificado precisa pertencer ao mesmo CNPJ utilizado no portal. Não é possível utilizar o certificado da matriz para baixar notas de uma filial.

### Exemplo

```json
{
  "cert_path": "caminho/para/certificado.pfx",
  "cert_pass": "minha_senha",
  "cnpj": "12345678000199",
  "output_dir": "./xml",
  "log_dir": "./logs",
  "file_prefix": "NFS-e",
  "delay_seconds": 2,
  "auto_start": false,
  "timeout": 30
}
```

## Execução

Linux/macOS:

```bash
python3 download_nfse_gui.py
```

Windows:

```cmd
python download_nfse_gui.py
```

O programa lê o `config.json`, faz login com o certificado e salva as notas no diretório configurado.
Os XMLs são nomeados seguindo o padrão `<prefixo>_AAAA-MM_<chave>.xml` definido
pela chave `file_prefix`.

A interface gráfica também possui um botão **Sobre** que exibe a versão do
aplicativo, o autor e o texto completo da licença MIT utilizada. O texto da
licença já está embutido no código, portanto não é necessário distribuir o
arquivo `LICENSE` junto com o executável.

## Gerar executável com PyInstaller

Para criar um executável standalone:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --noupx download_nfse_gui.py
```
O executável será gerado dentro da pasta `dist`.
Copie o `config.json` e o arquivo de certificado (`.pfx` ou `.pem`) para esse
diretório para que o programa consiga localizá-los em tempo de execução.

### Incluir configurações e recursos adicionais

Se sua aplicação precisar de outros arquivos, use `--add-data` para que o
PyInstaller os incorpore ao executável. O formato do argumento é
`<arquivo>;<destino>` no Windows ou `<arquivo>:<destino>` no Linux/macOS. Exemplo:

```bash
pyinstaller --onefile --noconsole --noupx \
  --add-data "config.json;." download_nfse_gui.py
```

Em modo `--onefile` todos os dados embutidos são extraídos para um diretório
temporário quando o executável é iniciado e removidos ao final da execução.

### Verificação de integridade

Para garantir que o binário não foi alterado, considere assinar digitalmente o
executável (por exemplo, utilizando **Authenticode** no Windows) ou publicar o
checksum SHA-256 para que os usuários possam conferir a integridade do arquivo.

Um script auxiliar `build_exe.sh` está disponível para automatizar essas etapas,
já utilizando a opção `--noconsole` e adicionando `--noupx` por padrão.

Executáveis gerados pelo PyInstaller podem disparar alertas falsos em alguns
antivírus. Caso isso ocorra, prefira incluir a opção `--noupx` ao gerar o
executável para evitar a compactação com UPX.

Além disso, o repositório possui um workflow do **GitHub Actions** que realiza
a compilação em um ambiente Windows. Ao enviar alterações para a branch
`main`, todo o conteúdo da pasta `dist` é disponibilizado como artefato na aba
*Actions*. O executável gerado recebe um sufixo no formato `0.<run>` e é
publicado automaticamente em uma release, como `download_nfse_gui_0.42.exe`.
O número dessa versão também aparece no título da janela do aplicativo.

## Testes

Para rodar a suíte de testes, instale o `pytest` em seu ambiente e execute:

```bash
pip install pytest
pytest
```

## Licença

Este projeto está licenciado sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
