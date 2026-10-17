"""Instalação do driver PKCS#11 do ePass2003 via script embutido no pacote."""

import os
import shutil
import subprocess
from importlib import resources


def instalar_driver() -> int:
    """Executa o instalar-driver.sh do pacote (com sudo, se preciso) e retorna o código de saída."""
    comando = ["bash"]
    if os.geteuid() != 0:
        if not shutil.which("sudo"):
            raise RuntimeError("é preciso ser root (sudo não encontrado)")
        comando = ["sudo", "bash"]

    script = resources.files(__package__) / "instalar-driver.sh"
    with resources.as_file(script) as caminho:
        return subprocess.run([*comando, str(caminho)]).returncode
