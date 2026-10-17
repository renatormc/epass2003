"""Registro do driver do token nos bancos NSS do usuário (Firefox, Chrome, LibreOffice, Okular)."""

import configparser
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

from .assinatura import MODULOS_PADRAO

DRIVER = MODULOS_PADRAO[0]
NOME_MODULO = "Token ePass 2003"

# Firefox recente (XDG) e antigo; o Snap só é avisado
BASES_FIREFOX = [Path(".config/mozilla/firefox"), Path(".mozilla/firefox")]
BASE_SNAP = Path("snap/firefox/common/.mozilla/firefox")


def _perfis(base: Path) -> list[Path]:
    """Pastas de perfil listadas no profiles.ini de ``base``."""
    ini = configparser.ConfigParser(interpolation=None)
    try:
        ini.read(base / "profiles.ini", encoding="utf-8")
    except configparser.Error:
        return []
    perfis = []
    for secao in ini.sections():
        if secao.startswith("Profile") and "Path" in ini[secao]:
            caminho = Path(ini[secao]["Path"])
            perfis.append(base / caminho if ini[secao].get("IsRelative", "1") == "1" else caminho)
    return perfis


def _tem_banco(pasta: Path) -> bool:
    return (pasta / "cert9.db").exists() or (pasta / "pkcs11.txt").exists()


def bancos_nss(criar: bool = True) -> tuple[list[Path], list[str]]:
    """Retorna (bancos NSS do usuário, avisos). Com ``criar``, cria o ~/.pki/nssdb se faltar."""
    casa = Path.home()
    bancos, avisos, vistos = [], [], set()
    for base in BASES_FIREFOX:
        for perfil in _perfis(casa / base):
            real = os.path.realpath(perfil)
            if real in vistos:
                continue
            vistos.add(real)
            if _tem_banco(perfil):
                bancos.append(perfil)
            elif perfil.is_dir():
                avisos.append(f"perfil nunca aberto, ignorado (abra o Firefox uma vez e rode de novo): {perfil}")

    nssdb = casa / ".pki" / "nssdb"
    if criar and not _tem_banco(nssdb):
        nssdb.mkdir(parents=True, exist_ok=True, mode=0o700)
        r = subprocess.run(
            ["certutil", "-N", "-d", f"sql:{nssdb}", "--empty-password"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            raise RuntimeError(f"não foi possível criar {nssdb}: {(r.stderr or r.stdout).strip()}")
    if _tem_banco(nssdb):
        bancos.append(nssdb)

    if _perfis(casa / BASE_SNAP):
        avisos.append("Firefox Snap encontrado e não configurado; veja a seção do Firefox Snap no epass.md.")
    return bancos, avisos


def _hosts_locais() -> set[str]:
    nome = socket.gethostname()
    hosts = {nome, "localhost", "127.0.0.1", "127.0.1.1"}
    try:
        hosts.update(socket.gethostbyname_ex(nome)[2])
    except OSError:
        pass
    return hosts


def em_uso(perfil: Path) -> bool:
    """O Firefox está com o perfil aberto? A trava ``lock`` -> ``host:+pid`` pode sobrar após fechar."""
    try:
        alvo = os.readlink(perfil / "lock")
    except OSError:
        return False
    host, _, pid = alvo.rpartition(":+")
    if host not in _hosts_locais() or not pid.isdigit():
        return True  # trava de outra máquina ou formato desconhecido: melhor não mexer
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def bibliotecas_registradas(banco: Path) -> list[str]:
    """Nomes dos módulos do banco cuja biblioteca é o driver do token (pelo caminho real)."""
    try:
        texto = (banco / "pkcs11.txt").read_text(errors="replace")
    except OSError:
        return []
    driver = os.path.realpath(DRIVER)
    nomes = []
    for bloco in texto.split("\n\n"):
        campos = dict(linha.split("=", 1) for linha in bloco.splitlines() if "=" in linha)
        biblioteca = campos.get("library", "").strip()
        if biblioteca and os.path.realpath(biblioteca) == driver:
            nomes.append(campos.get("name", "").strip())
    return nomes


def verificar_requisitos() -> None:
    if os.geteuid() == 0:
        raise RuntimeError("os navegadores são do usuário; rode sem sudo")
    for programa in ("modutil", "certutil"):
        if not shutil.which(programa):
            raise RuntimeError(f"{programa} não encontrado; rode: uv run epass2003 instalar-driver")
    if not Path(DRIVER).exists():
        raise RuntimeError(f"driver não encontrado em {DRIVER}; rode: uv run epass2003 instalar-driver")


def _modutil(banco: Path, *args: str) -> str | None:
    """Roda o modutil e retorna a mensagem de erro, ou None se deu certo."""
    r = subprocess.run(
        ["modutil", "-force", "-dbdir", f"sql:{banco}", *args],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if r.returncode == 0:
        return None
    return (r.stderr or r.stdout).strip() or f"modutil terminou com código {r.returncode}"


def configurar(bancos: list[Path], remover: bool = False) -> Iterator[tuple[str, Path]]:
    """Registra (ou remove) o driver em cada banco, gerando (status, banco) à medida que termina.

    Cada chamada ao modutil carrega o driver, o que leva alguns segundos.
    """
    for banco in bancos:
        if em_uso(banco):
            yield "em uso: feche o Firefox e rode de novo", banco
            continue
        nomes = bibliotecas_registradas(banco)
        if remover:
            if not nomes:
                yield "não estava configurado", banco
                continue
            erros = [e for nome in nomes if (e := _modutil(banco, "-delete", nome))]
            yield (f"falha: {erros[0]}" if erros else "removido"), banco
        elif nomes:
            yield "já configurado", banco
        else:
            erro = _modutil(banco, "-add", NOME_MODULO, "-libfile", DRIVER)
            yield (f"falha: {erro}" if erro else "configurado"), banco
