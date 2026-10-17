"""Atalho ``.desktop`` do epass2003-assinador no menu de aplicativos do usuário."""

import os
import re
import shutil
import subprocess
from pathlib import Path

NOME_ARQUIVO = "epass2003-assinador.desktop"

# Caracteres que obrigam a pôr o argumento entre aspas no Exec (Desktop Entry Specification)
RESERVADOS = re.compile(r"""[\s"'\\><~|&;$*?#()`]""")


def pasta_atalhos() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "applications"


def raiz_projeto() -> Path:
    """Pasta clonada do projeto: a primeira acima deste módulo com o pyproject.toml do epass2003."""
    for pasta in Path(__file__).resolve().parents:
        pyproject = pasta / "pyproject.toml"
        if pyproject.is_file() and re.search(r'^name = "epass2003"$', pyproject.read_text(), re.M):
            return pasta
    raise RuntimeError("o atalho exige o projeto clonado com git (pyproject.toml não encontrado)")


def argumento_exec(arg: str) -> str:
    if RESERVADOS.search(arg):
        arg = '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'
    # Regras de string do arquivo .desktop, aplicadas por cima das aspas
    return arg.replace("\\", "\\\\").replace("%", "%%")


def conteudo_atalho(uv: str, projeto: Path) -> str:
    comando = [uv, "run", "--project", str(projeto), "epass2003-assinador", "--ligado"]
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Assinador ePass2003\n"
        "Comment=Assinador local de PDFs com o token ePass2003\n"
        f"Exec={' '.join(argumento_exec(a) for a in comando)}\n"
        "Icon=application-pdf\n"
        "Terminal=false\n"
        "Categories=Office;\n"
        "StartupNotify=true\n"
    )


def _recusar_root() -> None:
    if os.geteuid() == 0:
        raise RuntimeError("o atalho é do usuário; rode sem sudo")


def _atualizar_menu(pasta: Path) -> None:
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(pasta)], check=False, capture_output=True)


def instalar_atalho() -> Path:
    """Grava (ou substitui) o atalho e retorna o caminho do arquivo."""
    _recusar_root()
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv não encontrado; instale com: curl -LsSf https://astral.sh/uv/install.sh | sh")
    conteudo = conteudo_atalho(str(Path(uv).absolute()), raiz_projeto())

    pasta = pasta_atalhos()
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / NOME_ARQUIVO
    arquivo.write_text(conteudo)
    arquivo.chmod(0o644)
    _atualizar_menu(pasta)
    return arquivo


def remover_atalho() -> Path | None:
    """Apaga o atalho e retorna o caminho apagado, ou None se não havia atalho."""
    _recusar_root()
    arquivo = pasta_atalhos() / NOME_ARQUIVO
    if not arquivo.exists():
        return None
    arquivo.unlink()
    _atualizar_menu(arquivo.parent)
    return arquivo
