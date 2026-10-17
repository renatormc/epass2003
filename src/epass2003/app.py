"""Assinador local compatível com o "ASSINADOR DIGITAL SSPGO" do Windows.

Sobe um servidor em ``localhost:3399``. Quando o site chama
``/assinarPdf?cpf=<base64>&fileDownload=<base64 da URL>``, baixa o PDF, pede o
PIN do token em um diálogo e responde com o PDF assinado em Base64.
"""

import base64
import binascii
import logging
import sys
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from werkzeug.serving import make_server

from .assinatura import (
    CpfNaoConfere,
    EPass2003Error,
    PinIncorreto,
    assinar_pdf_bytes,
    somente_digitos,
    tem_assinatura,
    verificar_pdf_assinado,
)

HOST, PORTA = "127.0.0.1", 3399
TEMPO_PIN = 300  # segundos esperando o usuário digitar o PIN
TAMANHO_MAXIMO = 100 * 1024 * 1024

log = logging.getLogger(__name__)


@dataclass
class PedidoPin:
    """Pedido de PIN feito pela thread do Flask à interface."""

    cpf: str
    url: str
    origem: str
    erro: str = ""
    acao: str = "assinar"  # "assinar" (com o token) ou "substituir" (PDF já assinado)
    arquivo: Path | None = None
    pin: str | None = None
    respondido: threading.Event = field(default_factory=threading.Event)
    dialogo: QDialog | None = None


class Ponte(QObject):
    """Sinais emitidos pela thread do Flask e tratados na thread da interface."""

    pedir_pin = Signal(object)
    expirou = Signal(object)
    status = Signal(str)


def criar_app(ponte: Ponte, teste: bool = False) -> Flask:
    app = Flask(__name__)
    uma_por_vez = threading.Lock()

    def erro(mensagem: str, status: int = 400):
        ponte.status.emit(f"Erro: {mensagem}")
        return jsonify(status=status, message=mensagem)

    def pedir_pin(pedido: PedidoPin) -> bool:
        """Mostra o diálogo e retorna False se o usuário cancelou ou o tempo acabou."""
        ponte.pedir_pin.emit(pedido)
        if not pedido.respondido.wait(TEMPO_PIN):
            ponte.expirou.emit(pedido)
            return False
        return bool(pedido.pin if pedido.acao == "assinar" else pedido.arquivo)

    def ler_substituto(caminho: Path) -> bytes:
        if caminho.stat().st_size > TAMANHO_MAXIMO:
            raise EPass2003Error("O PDF escolhido passa de 100 MB.")
        return caminho.read_bytes()

    @app.after_request
    def cors(resposta: Response) -> Response:
        # Sem CORS no modo de teste: sites não podem ler arquivos locais
        if request.path.startswith("/teste/"):
            return resposta
        resposta.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
        resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        resposta.headers["Access-Control-Allow-Headers"] = "*"
        # Chrome exige isto para sites da internet acessarem localhost
        if request.headers.get("Access-Control-Request-Private-Network"):
            resposta.headers["Access-Control-Allow-Private-Network"] = "true"
        return resposta

    @app.get("/assinarPdf")
    def assinar():
        try:
            cpf = somente_digitos(base64.b64decode(request.args.get("cpf", "")).decode())
            url = base64.b64decode(request.args["fileDownload"]).decode()
        except (KeyError, binascii.Error, UnicodeDecodeError):
            return erro("Parâmetros inválidos: esperados cpf e fileDownload em Base64.")
        if urlparse(url).scheme not in ("http", "https"):
            return erro("URL de download inválida.")
        origem = request.headers.get("Origin") or request.headers.get("Referer") or "desconhecida"

        with uma_por_vez:
            ponte.status.emit(f"Baixando PDF de {urlparse(url).netloc}...")
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    pdf = r.read(TAMANHO_MAXIMO + 1)
            except OSError as e:
                return erro(f"Não foi possível baixar o PDF: {e}")
            if len(pdf) > TAMANHO_MAXIMO or not pdf.startswith(b"%PDF"):
                return erro("O arquivo baixado não é um PDF válido.")

            ja_assinado = tem_assinatura(pdf)
            pedido = PedidoPin(cpf=cpf, url=url, origem=origem)
            while True:
                if not pedir_pin(pedido):
                    return erro("Assinatura cancelada pelo usuário.")
                if pedido.acao == "substituir":
                    ponte.status.emit(f"Conferindo {pedido.arquivo.name}...")
                    try:
                        substituto = ler_substituto(pedido.arquivo)
                        verificar_pdf_assinado(substituto, cpf or None)
                    except CpfNaoConfere:
                        return erro(f"O CPF informado ({cpf}) não corresponde ao PDF assinado escolhido.", 500)
                    except (OSError, EPass2003Error) as e:
                        motivo = e if isinstance(e, EPass2003Error) else f"Não foi possível ler o arquivo: {e}"
                        pedido = PedidoPin(
                            cpf=cpf, url=url, origem=origem, erro=str(motivo),
                            acao="substituir", arquivo=pedido.arquivo,
                        )
                        continue
                    ponte.status.emit("PDF escolhido enviado ao site.")
                    return Response(base64.b64encode(substituto), mimetype="text/plain")

                ponte.status.emit("Assinando...")
                try:
                    assinado = assinar_pdf_bytes(pdf, pin=pedido.pin, cpf=cpf or None, texto_lateral=True)
                    break
                except PinIncorreto:
                    pedido = PedidoPin(
                        cpf=cpf,
                        url=url,
                        origem=origem,
                        erro="PIN incorreto. Atenção: erros seguidos bloqueiam o token.",
                    )
                except CpfNaoConfere:
                    return erro(f"O CPF informado ({cpf}) não corresponde ao TOKEN inserido.", 500)
                except EPass2003Error as e:
                    return erro(str(e))

        if ja_assinado:
            ponte.status.emit("PDF assinado e enviado ao site. Ele já estava assinado: texto lateral omitido.")
        else:
            ponte.status.emit("PDF assinado e enviado ao site.")
        return Response(base64.b64encode(assinado), mimetype="text/plain")

    if teste:

        @app.get("/teste/pdf")
        def pdf_de_teste():
            """Entrega um PDF do disco para testar o /assinarPdf sem um sistema web."""
            caminho = Path(request.args.get("caminho", ""))
            if not caminho.is_absolute():
                return jsonify(status=400, message="Informe o caminho absoluto do PDF em 'caminho'."), 400
            try:
                if not caminho.is_file():
                    raise FileNotFoundError(caminho)
                if caminho.stat().st_size > TAMANHO_MAXIMO:
                    pdf = b""
                else:
                    pdf = caminho.read_bytes()
            except OSError:
                return jsonify(status=404, message=f"Arquivo não encontrado: {caminho}"), 404
            if not pdf.startswith(b"%PDF"):
                return jsonify(status=415, message=f"O arquivo não é um PDF válido: {caminho}"), 415
            return Response(pdf, mimetype="application/pdf")

    return app


class DialogoPin(QDialog):
    def __init__(self, pedido: PedidoPin, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Assinar PDF")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(420)

        self.arquivo = pedido.arquivo

        self.form = form = QFormLayout()
        form.addRow("Site:", QLabel(pedido.origem))
        form.addRow("Arquivo:", QLabel(urlparse(pedido.url).netloc))
        if pedido.cpf:
            form.addRow("CPF:", QLabel(pedido.cpf))
        self.acao = QComboBox()
        self.acao.addItem("Assinar", "assinar")
        self.acao.addItem("Substituir", "substituir")
        form.addRow("Ação:", self.acao)

        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setPlaceholderText("PIN do token")
        form.addRow("Senha:", self.pin)

        # Modo "Substituir": envia um PDF já assinado por outra ferramenta
        self.escolher = QPushButton("Escolher PDF…")
        self.escolher.clicked.connect(self.escolher_arquivo)
        self.nome_arquivo = QLabel()
        self.nome_arquivo.setWordWrap(True)
        linha_arquivo = QWidget()
        caixa_arquivo = QHBoxLayout(linha_arquivo)
        caixa_arquivo.setContentsMargins(0, 0, 0, 0)
        caixa_arquivo.addWidget(self.escolher)
        caixa_arquivo.addWidget(self.nome_arquivo, 1)
        form.addRow("PDF assinado:", linha_arquivo)
        self.linha_arquivo = linha_arquivo

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.confirmar = botoes.addButton("Assinar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.confirmar.setDefault(True)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if pedido.erro:
            aviso = QLabel(pedido.erro)
            aviso.setStyleSheet("color: #c62828; font-weight: bold;")
            aviso.setWordWrap(True)
            layout.addWidget(aviso)
        layout.addLayout(form)
        layout.addWidget(botoes)

        self.acao.currentIndexChanged.connect(self.atualizar)
        self.acao.setCurrentIndex(self.acao.findData(pedido.acao))
        self.atualizar()

    @Slot()
    def atualizar(self):
        substituir = self.acao.currentData() == "substituir"
        self.form.setRowVisible(self.pin, not substituir)
        self.form.setRowVisible(self.linha_arquivo, substituir)
        self.nome_arquivo.setText(self.arquivo.name if self.arquivo else "nenhum arquivo escolhido")
        self.confirmar.setText("Enviar" if substituir else "Assinar")
        self.confirmar.setEnabled(not substituir or self.arquivo is not None)
        (self.escolher if substituir else self.pin).setFocus()

    @Slot()
    def escolher_arquivo(self):
        pasta = str(self.arquivo.parent if self.arquivo else Path.home())
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher PDF assinado", pasta, "PDF (*.pdf)")
        if caminho:
            self.arquivo = Path(caminho)
            self.atualizar()


class JanelaPrincipal(QMainWindow):
    def __init__(self, teste: bool = False):
        super().__init__()
        self.setWindowTitle("Assinador ePass2003" + (" (modo de teste)" if teste else ""))
        self.servidor = None
        self.pedidos: list[PedidoPin] = []

        self.ponte = Ponte()
        self.ponte.pedir_pin.connect(self.mostrar_dialogo)
        self.ponte.expirou.connect(self.fechar_dialogo)
        self.ponte.status.connect(self.mostrar_status)
        self.app_flask = criar_app(self.ponte, teste)

        self.botao = QPushButton("Ligar")
        self.botao.setCheckable(True)
        self.botao.setMinimumHeight(48)
        self.botao.toggled.connect(self.alternar)
        self.status = QLabel("Desligado")
        self.status.setWordWrap(True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.botao)
        layout.addWidget(self.status)
        self.setCentralWidget(central)
        self.resize(360, 130)

    @Slot(bool)
    def alternar(self, ligar: bool):
        if ligar:
            try:
                self.servidor = make_server(HOST, PORTA, self.app_flask, threaded=True)
            except OSError as e:
                QMessageBox.critical(self, "Erro", f"Não foi possível usar a porta {PORTA}: {e}")
                self.botao.setChecked(False)
                return
            threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
            self.botao.setText("Desligar")
            self.mostrar_status(f"Ligado em http://localhost:{PORTA}")
        elif self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()
            self.servidor = None
            for pedido in list(self.pedidos):
                self.fechar_dialogo(pedido)
            self.botao.setText("Ligar")
            self.mostrar_status("Desligado")

    @Slot(object)
    def mostrar_dialogo(self, pedido: PedidoPin):
        self.pedidos.append(pedido)
        pedido.dialogo = DialogoPin(pedido, self)
        pedido.dialogo.show()
        pedido.dialogo.raise_()
        pedido.dialogo.activateWindow()
        dialogo = pedido.dialogo
        aceito = dialogo.exec() == QDialog.DialogCode.Accepted
        pedido.acao = dialogo.acao.currentData()
        pedido.pin = dialogo.pin.text() if aceito and pedido.acao == "assinar" else None
        pedido.arquivo = dialogo.arquivo if aceito and pedido.acao == "substituir" else None
        pedido.dialogo = None
        self.pedidos.remove(pedido)
        pedido.respondido.set()

    @Slot(object)
    def fechar_dialogo(self, pedido: PedidoPin):
        if pedido.dialogo:
            pedido.dialogo.reject()

    @Slot(str)
    def mostrar_status(self, texto: str):
        self.status.setText(texto)
        log.info(texto)

    def closeEvent(self, evento):
        self.botao.setChecked(False)
        super().closeEvent(evento)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    app = QApplication(sys.argv)
    janela = JanelaPrincipal(teste="--test" in sys.argv)
    janela.show()
    if "--ligado" in sys.argv:
        janela.botao.setChecked(True)
    sys.exit(app.exec())
