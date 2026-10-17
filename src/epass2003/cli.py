"""Linha de comando: ``epass2003 assinar``, ``instalar-driver``, ``instalar-atalho``,
``configurar-navegadores`` e ``testar-assinador``."""

import argparse
import base64
import binascii
import getpass
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode

from .assinatura import TEXTO_PADRAO, EPass2003Error, assinar_pdf
from .atalho import instalar_atalho, remover_atalho
from .driver import instalar_driver
from . import navegadores

# Mesmo endereço do epass2003-assinador (não importamos app.py para não exigir PySide6)
ASSINADOR = "http://127.0.0.1:3399"


def _assinar(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.imagem and not args.visivel:
        parser.error("--imagem exige --visivel")

    pagina, caixa = 0, None
    if args.visivel:
        try:
            pagina, *caixa = (int(v) for v in args.visivel.split(","))
        except ValueError:
            parser.error("--visivel deve ser PAG,X1,Y1,X2,Y2 (números inteiros)")
        if len(caixa) != 4:
            parser.error("--visivel deve ser PAG,X1,Y1,X2,Y2")

    pin = args.pin or os.environ.get("EPASS_PIN") or getpass.getpass("PIN do token: ")
    saida = assinar_pdf(
        args.entrada,
        args.saida,
        pin=pin,
        modulo=args.modulo,
        slot=args.slot,
        certificado=args.certificado,
        motivo=args.motivo,
        local=args.local,
        tsa=args.tsa,
        pagina=pagina,
        caixa=tuple(caixa) if caixa else None,
        imagem=args.imagem,
        texto=args.texto,
        opacidade=args.opacidade,
    )
    print(f"PDF assinado salvo em: {saida}")


def _mensagem_json(corpo: bytes) -> str | None:
    """Retorna o ``message`` de uma resposta JSON do assinador, ou None se não for JSON."""
    try:
        return json.loads(corpo)["message"]
    except (ValueError, KeyError, TypeError):
        return None


def _testar_assinador(args: argparse.Namespace) -> None:
    pdf = args.pdf.resolve()
    if not pdf.is_file():
        raise EPass2003Error(f"arquivo não encontrado: {pdf}")
    saida = args.saida or args.pdf.with_name(f"{pdf.stem}-assinado.pdf")
    url_pdf = f"{ASSINADOR}/teste/pdf?caminho={quote(str(pdf))}"

    # Verificação prévia: o assinador está ligado, em modo de teste, e aceita o arquivo?
    try:
        with urllib.request.urlopen(url_pdf, timeout=10):
            pass
    except urllib.error.HTTPError as e:
        mensagem = _mensagem_json(e.read())
        if mensagem:
            raise EPass2003Error(mensagem) from e
        raise EPass2003Error(
            "o assinador não está em modo de teste; reinicie-o com: epass2003-assinador --test --ligado"
        ) from e
    except OSError as e:
        raise EPass2003Error(
            f"o assinador não responde em {ASSINADOR}; inicie-o com: epass2003-assinador --test --ligado"
        ) from e

    parametros = urlencode(
        {
            "nocache": int(time.time() * 1000),
            "cpf": base64.b64encode((args.cpf or "").encode()).decode(),
            "fileDownload": base64.b64encode(url_pdf.encode()).decode(),
        }
    )
    print("Aguardando o PIN na janela do assinador...")
    # Sem timeout: o usuário pode levar minutos para digitar o PIN
    try:
        with urllib.request.urlopen(f"{ASSINADOR}/assinarPdf?{parametros}") as r:
            corpo = r.read()
    except OSError as e:
        raise EPass2003Error(f"falha ao falar com o assinador: {e}") from e

    if (mensagem := _mensagem_json(corpo)) is not None:
        raise EPass2003Error(mensagem)
    try:
        assinado = base64.b64decode(corpo, validate=True)
    except binascii.Error as e:
        raise EPass2003Error("resposta inesperada do assinador") from e
    saida.write_bytes(assinado)
    print(f"PDF assinado salvo em: {saida}")


def _configurar_navegadores(remover: bool) -> int:
    navegadores.verificar_requisitos()
    bancos, avisos = navegadores.bancos_nss(criar=not remover)
    print("Cada banco pode levar uns 20 segundos (o driver é carregado a cada operação).")
    pendente = False
    for status, banco in navegadores.configurar(bancos, remover):
        print(f"{status:40} {banco}", flush=True)
        pendente |= status.startswith(("em uso", "falha"))
    for aviso in avisos:
        print(f"Aviso: {aviso}")
    if not remover:
        print("Reinicie o Chrome/Chromium e o Okular, se estiverem abertos, para que vejam o token.")
    return 1 if pendente else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="epass2003", description="Ferramentas para o token ePass2003.")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser(
        "instalar-driver", help="instala o driver PKCS#11 e o serviço PC/SC (Debian/Ubuntu, usa sudo)"
    )

    a = sub.add_parser("instalar-atalho", help="põe o epass2003-assinador no menu de aplicativos do usuário")
    a.add_argument("--remover", action="store_true", help="remove o atalho do menu")

    n = sub.add_parser(
        "configurar-navegadores",
        help="registra o token no Firefox, Chrome/Chromium, LibreOffice e Okular do usuário",
    )
    n.add_argument("--remover", action="store_true", help="remove o token dos navegadores")

    p = sub.add_parser("assinar", help="assina um PDF com o token")
    p.add_argument("entrada", type=Path, help="PDF a ser assinado")
    p.add_argument("-o", "--saida", type=Path, help="PDF assinado (padrão: <entrada>-assinado.pdf)")
    p.add_argument("--modulo", default=None, help="biblioteca PKCS#11 do token")
    p.add_argument("--slot", type=int, default=None, help="número do slot do token")
    p.add_argument("--certificado", help="label do certificado no token")
    p.add_argument("--pin", help="PIN do token (padrão: variável EPASS_PIN; se ausente, será pedido)")
    p.add_argument("--motivo", help="motivo da assinatura")
    p.add_argument("--local", help="local da assinatura")
    p.add_argument("--tsa", help="URL de um servidor de carimbo de tempo (RFC 3161)")
    p.add_argument(
        "--visivel",
        metavar="PAG,X1,Y1,X2,Y2",
        help="cria assinatura visível na página (0 = primeira) e retângulo, em pontos",
    )
    p.add_argument("--imagem", type=Path, help="imagem (PNG, JPG...) exibida na assinatura visível")
    p.add_argument(
        "--texto",
        default=TEXTO_PADRAO,
        help="texto da assinatura visível; aceita %%(signer)s e %%(ts)s ('' para só a imagem)",
    )
    p.add_argument("--opacidade", type=float, default=1.0, help="opacidade da imagem, de 0 a 1 (padrão: 1)")

    t = sub.add_parser(
        "testar-assinador",
        help="assina um PDF local pelo epass2003-assinador (que deve estar rodando com --test)",
    )
    t.add_argument("pdf", type=Path, help="PDF a ser assinado")
    t.add_argument("-o", "--saida", type=Path, help="PDF assinado (padrão: <pdf>-assinado.pdf)")
    t.add_argument("--cpf", help="CPF do titular; o assinador só usará certificados dele")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.comando == "instalar-driver":
        try:
            sys.exit(instalar_driver())
        except RuntimeError as e:
            sys.exit(f"Erro: {e}")

    if args.comando == "configurar-navegadores":
        try:
            sys.exit(_configurar_navegadores(args.remover))
        except (RuntimeError, OSError) as e:
            sys.exit(f"Erro: {e}")

    if args.comando == "instalar-atalho":
        try:
            if not args.remover:
                print(f"Atalho criado em: {instalar_atalho()}")
            elif removido := remover_atalho():
                print(f"Atalho removido: {removido}")
            else:
                print("Não havia atalho para remover.")
        except RuntimeError as e:
            sys.exit(f"Erro: {e}")
        return

    try:
        if args.comando == "testar-assinador":
            _testar_assinador(args)
        else:
            _assinar(args, p)
    except EPass2003Error as e:
        sys.exit(f"Erro: {e}")
