"""Assinatura de PDFs com o certificado guardado em um token ePass2003 (PKCS#11)."""

import io
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pkcs11
from asn1crypto import x509
from pkcs11 import Attribute, ObjectClass
from pyhanko import stamp
from pyhanko.pdf_utils import generic, images, layout
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign import pkcs11 as p11_signers
from pyhanko.sign.general import SigningError
from pyhanko.sign.validation.generic_cms import validate_sig_integrity

log = logging.getLogger(__name__)

MODULOS_PADRAO = [
    "/usr/lib/libcastle.so.1.0.0",  # driver da Feitian/Soluti
    "/usr/lib/opensc-pkcs11.so",  # OpenSC também suporta o ePass2003
]

TEXTO_PADRAO = "Assinado digitalmente por\n%(signer)s\nData: %(ts)s"

# otherName ICP-Brasil com os dados da pessoa física: nascimento (8 dígitos) + CPF (11) + ...
OID_PF_DADOS = "2.16.76.1.3.1"

TEXTO_LATERAL = "Assinado eletronicamente por %s"
TAMANHO_LATERAL = 8  # pontos
MARGEM_LATERAL = 28.35  # 1 cm da borda esquerda até o corpo do texto
FONTE_LATERAL = "/F_epass"

# Larguras da Helvetica (AFM, em 1/1000 do corpo) dos caracteres 32 a 126. Letras
# acentuadas têm a largura da letra base, e o resto usa 556.
_LARGURAS = dict(zip(map(chr, range(32, 127)), map(int, """
278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 556 556 556 556 556 556
556 556 556 556 278 278 584 584 584 556 1015 667 667 722 722 667 611 778 722 278 500 667
556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 333 556
556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 278 556 500 722
500 500 500 334 260 334 584""".split())))


class EPass2003Error(Exception):
    """Erro ao localizar o driver, o token ou o certificado."""


class PinIncorreto(EPass2003Error):
    """O PIN informado não confere."""


class CpfNaoConfere(EPass2003Error):
    """Nenhum certificado do token pertence ao CPF informado."""


def modulo_padrao() -> str:
    """Retorna a primeira biblioteca PKCS#11 conhecida que existir no sistema."""
    for caminho in MODULOS_PADRAO:
        if Path(caminho).exists():
            return caminho
    raise EPass2003Error(
        "Nenhuma biblioteca PKCS#11 encontrada; instale o driver "
        "(epass2003 instalar-driver) ou informe o módulo."
    )


def somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def cpfs_do_certificado(cert: x509.Certificate) -> set[str]:
    """CPFs do titular, lidos do CN ("NOME:CPF") e do otherName ICP-Brasil."""
    cpfs = set()
    cn = cert.subject.native.get("common_name") or ""
    if m := re.search(r":(\d{11})$", cn):
        cpfs.add(m.group(1))
    for nome in cert.subject_alt_name_value or []:
        if nome.name == "other_name" and nome.chosen["type_id"].dotted == OID_PF_DADOS:
            valor = nome.chosen["value"].parsed.native
            if isinstance(valor, bytes):
                valor = valor.decode("latin-1")
            if len(cpf := valor[8:19]) == 11 and cpf.isdigit():
                cpfs.add(cpf)
    return cpfs


def estilo_carimbo(
    imagem: Path | None, texto: str, opacidade: float, largura: int
) -> stamp.TextStampStyle:
    """Com imagem e texto, a imagem ocupa ~40% à esquerda e o texto o restante."""
    meio = layout.AxisAlignment.ALIGN_MID
    layout_imagem = layout.SimpleBoxLayoutRule(x_align=meio, y_align=meio)
    layout_texto = None
    if imagem and texto:
        corte = int(largura * 0.4)
        layout_imagem = layout.SimpleBoxLayoutRule(
            x_align=meio, y_align=meio, margins=layout.Margins(right=largura - corte)
        )
        layout_texto = layout.SimpleBoxLayoutRule(
            x_align=layout.AxisAlignment.ALIGN_MIN,
            y_align=meio,
            margins=layout.Margins(left=corte + 5, right=2),
        )
    return stamp.TextStampStyle(
        stamp_text=texto,
        background=images.PdfImage(str(imagem)) if imagem else None,
        background_layout=layout_imagem,
        background_opacity=opacidade,
        inner_content_layout=layout_texto,
        timestamp_format="%d/%m/%Y %H:%M:%S %Z",
        border_width=0,
    )


def nome_do_titular(cert: x509.Certificate) -> str:
    """Nome do titular: o CN sem o sufixo ":CPF" dos certificados ICP-Brasil."""
    cn = cert.subject.native.get("common_name") or ""
    return re.sub(r":\d{11}$", "", cn)


def tem_assinatura(pdf: bytes) -> bool:
    """Indica se o PDF já tem alguma assinatura preenchida."""
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf))
    return any(fields.enumerate_sig_fields(writer, filled_status=True))


def verificar_pdf_assinado(pdf: bytes, cpf: str | None = None) -> None:
    """Confere um PDF assinado por qualquer ferramenta, sem avaliar a cadeia de confiança.

    Exige ao menos uma assinatura íntegra e, com ``cpf``, que uma delas seja de um
    certificado desse titular (senão lança ``CpfNaoConfere``).
    """
    try:
        assinaturas = PdfFileReader(io.BytesIO(pdf)).embedded_signatures
    except Exception as e:
        raise EPass2003Error("O arquivo escolhido não é um PDF válido.") from e
    if not assinaturas:
        raise EPass2003Error("O PDF escolhido não está assinado.")

    integras = []
    for sig in assinaturas:
        try:
            intacta, valida = validate_sig_integrity(
                sig.signer_info, sig.signer_cert, "data", sig.compute_digest()
            )
        except Exception:
            continue
        if intacta and valida:
            integras.append(sig.signer_cert)
    if not integras:
        raise EPass2003Error("Nenhuma assinatura do PDF escolhido é íntegra.")

    cpf = somente_digitos(cpf) if cpf else None
    if cpf and not any(cpf in cpfs_do_certificado(cert) for cert in integras):
        raise CpfNaoConfere(f"O CPF informado ({cpf}) não corresponde ao PDF assinado escolhido.")


def _largura_texto(texto: str, tamanho: float) -> float:
    def largura(c: str) -> int:
        base = unicodedata.normalize("NFD", c)[0]
        return _LARGURAS.get(c) or _LARGURAS.get(base, 556)

    return sum(map(largura, texto)) * tamanho / 1000


def _atributo_herdado(pagina: generic.DictionaryObject, nome: str):
    while pagina is not None:
        if nome in pagina:
            return pagina[nome]
        pagina = pagina["/Parent"] if "/Parent" in pagina else None
    return None


def _matriz_visual(pagina: generic.DictionaryObject) -> tuple[list[float], float, float]:
    """Matriz que leva da página como é exibida (sem rotação) ao espaço do usuário.

    Retorna (matriz cm, largura exibida, altura exibida).
    """
    caixa = _atributo_herdado(pagina, "/CropBox") or _atributo_herdado(pagina, "/MediaBox")
    x0, y0, x1, y1 = (float(v) for v in caixa)
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    w, h = x1 - x0, y1 - y0
    rotacao = int(_atributo_herdado(pagina, "/Rotate") or 0) % 360
    if rotacao == 90:
        return [0, 1, -1, 0, x0 + w, y0], h, w
    if rotacao == 180:
        return [-1, 0, 0, -1, x0 + w, y0 + h], w, h
    if rotacao == 270:
        return [0, -1, 1, 0, x0, y0 + h], h, w
    return [1, 0, 0, 1, x0, y0], w, h


def aplicar_texto_lateral(writer: IncrementalPdfFileWriter, texto: str) -> None:
    """Escreve ``texto`` na vertical, na margem esquerda de todas as páginas."""
    fonte = writer.add_object(
        generic.DictionaryObject(
            {
                generic.NameObject("/Type"): generic.NameObject("/Font"),
                generic.NameObject("/Subtype"): generic.NameObject("/Type1"),
                generic.NameObject("/BaseFont"): generic.NameObject("/Helvetica"),
                generic.NameObject("/Encoding"): generic.NameObject("/WinAnsiEncoding"),
            }
        )
    )
    recursos = generic.DictionaryObject(
        {
            generic.NameObject("/Font"): generic.DictionaryObject(
                {generic.NameObject(FONTE_LATERAL): fonte}
            )
        }
    )
    codificado = texto.encode("cp1252", errors="replace").hex().upper()
    largura = _largura_texto(texto, TAMANHO_LATERAL)
    # Isola o conteúdo original, que pode deixar transformações ou cores em aberto
    abre = writer.add_object(generic.StreamObject(stream_data=b"q\n"))

    for indice in range(int(writer.root["/Pages"]["/Count"])):
        pagina_ref, _ = writer.find_page_for_modification(indice)
        pagina = pagina_ref.get_object()
        matriz, _, altura = _matriz_visual(pagina)
        # Texto girado 90° (lido de baixo para cima); o corpo fica à esquerda da linha base
        x = MARGEM_LATERAL + TAMANHO_LATERAL
        y = (altura - largura) / 2
        ops = (
            "Q q {} cm BT {} {} Tf 0.4 g 0 1 -1 0 {:.2f} {:.2f} Tm <{}> Tj ET Q\n".format(
                " ".join(f"{v:g}" for v in matriz), FONTE_LATERAL, TAMANHO_LATERAL, x, y, codificado
            )
        )
        desenho = writer.add_object(generic.StreamObject(stream_data=ops.encode()))
        if "/Contents" not in pagina:  # página em branco
            pagina[generic.NameObject("/Contents")] = writer.add_object(generic.ArrayObject())
            writer.mark_update(pagina_ref)
        writer.add_stream_to_page(indice, abre, prepend=True)
        writer.add_stream_to_page(indice, desenho, recursos)


def escolher_certificado(
    session: pkcs11.Session, label: str | None = None, cpf: str | None = None
) -> tuple[bytes, str, x509.Certificate]:
    """Retorna (id, label, certificado) do certificado a usar.

    Considera só certificados com chave privada correspondente e, se informados,
    com o ``label`` e o ``cpf`` pedidos. Entre os válidos, usa o que vence por último.
    """
    ids_chaves = {
        k[Attribute.ID] for k in session.get_objects({Attribute.CLASS: ObjectClass.PRIVATE_KEY})
    }
    cpf = somente_digitos(cpf) if cpf else None
    agora = datetime.now(timezone.utc)
    candidatos, vencidos, outros_cpfs = [], [], False
    for obj in session.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE}):
        cert_id, cert_label = obj[Attribute.ID], obj[Attribute.LABEL]
        if cert_id not in ids_chaves or (label is not None and cert_label != label):
            continue
        cert = x509.Certificate.load(obj[Attribute.VALUE])
        if cpf and cpf not in cpfs_do_certificado(cert):
            outros_cpfs = True
            continue
        validade = cert["tbs_certificate"]["validity"]
        inicio, fim = validade["not_before"].native, validade["not_after"].native
        (candidatos if inicio <= agora <= fim else vencidos).append((fim, cert_id, cert_label, cert))

    if not candidatos:
        if vencidos:
            raise EPass2003Error("O certificado do token está vencido.")
        if outros_cpfs:
            raise CpfNaoConfere(f"O CPF informado ({cpf}) não corresponde ao certificado do token.")
        raise EPass2003Error("Nenhum certificado com chave privada encontrado no token.")
    candidatos.sort(key=lambda c: c[0], reverse=True)
    if len(candidatos) > 1:
        log.warning(
            "Vários certificados válidos encontrados (%s); usando %s.",
            ", ".join(nome for _, _, nome, _ in candidatos),
            candidatos[0][2],
        )
    _, cert_id, cert_label, cert = candidatos[0]
    return cert_id, cert_label, cert


def _assinar_com_signer(
    pdf: bytes,
    signer: signers.Signer,
    titular: str,
    *,
    motivo: str | None = None,
    local: str | None = None,
    tsa: str | None = None,
    pagina: int = 0,
    caixa: tuple[int, int, int, int] | None = None,
    imagem: Path | None = None,
    texto: str = TEXTO_PADRAO,
    opacidade: float = 1.0,
    texto_lateral: bool = False,
) -> bytes:
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf))

    # Evita conflito de nome se o PDF já tiver assinaturas
    existentes = {nome for nome, *_ in fields.enumerate_sig_fields(writer)}
    nome_campo, n = "Assinatura1", 1
    while nome_campo in existentes:
        n += 1
        nome_campo = f"Assinatura{n}"

    if texto_lateral:
        # Alterar as páginas de um PDF já assinado invalidaria as assinaturas anteriores
        if any(fields.enumerate_sig_fields(writer, filled_status=True)):
            log.warning("PDF já assinado: texto lateral omitido.")
        else:
            aplicar_texto_lateral(writer, TEXTO_LATERAL % titular)

    largura = 0
    if caixa:
        largura = abs(caixa[2] - caixa[0])
        fields.append_signature_field(
            writer, fields.SigFieldSpec(nome_campo, on_page=pagina, box=tuple(caixa))
        )

    meta = signers.PdfSignatureMetadata(
        field_name=nome_campo,
        md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason=motivo,
        location=local,
    )
    pdf_signer = signers.PdfSigner(
        meta,
        signer=signer,
        timestamper=timestamps.HTTPTimeStamper(tsa) if tsa else None,
        stamp_style=estilo_carimbo(imagem, texto, opacidade, largura),
    )
    saida = io.BytesIO()
    pdf_signer.sign_pdf(writer, output=saida)
    return saida.getvalue()


def assinar_pdf_bytes(
    pdf: bytes,
    *,
    pin: str,
    cpf: str | None = None,
    modulo: str | None = None,
    slot: int | None = None,
    certificado: str | None = None,
    motivo: str | None = None,
    local: str | None = None,
    tsa: str | None = None,
    pagina: int = 0,
    caixa: tuple[int, int, int, int] | None = None,
    imagem: str | Path | None = None,
    texto: str = TEXTO_PADRAO,
    opacidade: float = 1.0,
    texto_lateral: bool = False,
) -> bytes:
    """Assina o PDF (PAdES) com o token e retorna o PDF assinado.

    Com ``cpf``, só usa certificados desse titular (senão lança ``CpfNaoConfere``).
    A assinatura só é visível quando ``caixa`` (x1, y1, x2, y2, em pontos) é
    informada; ela é desenhada na página ``pagina`` (0 = primeira). Com
    ``texto_lateral``, todas as páginas recebem "Assinado eletronicamente por
    <titular>" na margem esquerda, exceto se o PDF já estiver assinado.
    """
    imagem = Path(imagem) if imagem else None
    if imagem and not caixa:
        raise ValueError("imagem exige caixa (assinatura visível)")
    modulo = modulo or modulo_padrao()

    try:
        with p11_signers.open_pkcs11_session(modulo, slot_no=slot, user_pin=pin) as session:
            cert_id, cert_label, cert = escolher_certificado(session, certificado, cpf)
            log.info("Assinando com: %s", cert_label)
            signer = p11_signers.PKCS11Signer(session, cert_id=cert_id, key_id=cert_id)
            return _assinar_com_signer(
                pdf,
                signer,
                nome_do_titular(cert),
                motivo=motivo,
                local=local,
                tsa=tsa,
                pagina=pagina,
                caixa=caixa,
                imagem=imagem,
                texto=texto,
                opacidade=opacidade,
                texto_lateral=texto_lateral,
            )
    except (pkcs11.exceptions.PinIncorrect, pkcs11.exceptions.PinLenRange) as e:
        raise PinIncorreto("PIN incorreto.") from e
    except pkcs11.exceptions.PinLocked as e:
        raise EPass2003Error("PIN bloqueado; desbloqueie o token com o PUK.") from e
    except pkcs11.exceptions.PKCS11Error as e:
        raise EPass2003Error(f"Erro de comunicação com o token: {e or type(e).__name__}") from e
    except SigningError as e:
        raise EPass2003Error(f"Erro ao assinar: {e}") from e


def assinar_pdf(
    entrada: str | Path,
    saida: str | Path | None = None,
    **opcoes,
) -> Path:
    """Assina o arquivo ``entrada`` e retorna o caminho do PDF assinado.

    ``saida`` padrão: ``<entrada>-assinado.pdf``. As demais opções (``pin``,
    ``cpf``, ``caixa``...) são as de :func:`assinar_pdf_bytes`.
    """
    entrada = Path(entrada)
    saida = Path(saida) if saida else entrada.with_name(f"{entrada.stem}-assinado.pdf")
    saida.write_bytes(assinar_pdf_bytes(entrada.read_bytes(), **opcoes))
    return saida
