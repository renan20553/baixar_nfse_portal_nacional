from pathlib import Path

def ler_ultimo_nsu(caminho: Path) -> str:
    """Read the last NSU stored in the given file path."""
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read().strip()


def salvar_ultimo_nsu(nsu: str, caminho: Path) -> None:
    """Save the given NSU string to the given file path."""
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(str(nsu))
