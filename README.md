# epass2003

Aplicativo para usar o token criptográfico **ePass2003 (Soluti/Feitian)** no Linux (Debian/Ubuntu):

- **instala o driver** PKCS#11 (`libcastle`) e configura o serviço PC/SC com um único comando;
- **assina PDFs** (padrão PAdES) com o certificado do token, com suporte a assinatura visível, imagem de rubrica e carimbo de tempo;
- **assinador local para sites**: aplicativo (PySide6 + Flask) que atende o protocolo `localhost:3399/assinarPdf` usado por sistemas web que, no Windows, assinam PDFs por meio de um assinador local.

Para usar o token nos navegadores e no Okular, veja a seção [Configurar navegadores e o Okular](#configurar-navegadores-e-o-okular). Para assinar com outros programas (Assinador Serpro, LibreOffice), veja o [guia manual](epass.md).

## Requisitos

- Debian ou Ubuntu x86_64, com conexão à internet na instalação
- `git` e o gerenciador de projetos Python [`uv`](https://docs.astral.sh/uv/) (instruções abaixo; o `uv` baixa sozinho o Python, se preciso)
- Token ePass2003 com certificado instalado

## Instalação

1. Instale o `git` e o `curl`:

   ```bash
   sudo apt install -y git curl
   ```

2. Instale o `uv` com o script oficial e depois **abra um novo terminal**, para que o comando `uv` passe a ser encontrado:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Confira com `uv --version`.

3. Clone o projeto e instale as dependências:

   ```bash
   git clone https://github.com/renatormc/epass2003.git
   cd epass2003
   uv sync
   ```

Todos os comandos abaixo devem ser rodados **dentro da pasta `epass2003`**, sempre com `uv run` na frente. Os PDFs podem estar em qualquer lugar: informe o caminho completo deles, como `~/Documentos/documento.pdf`.

### Atualização

```bash
cd epass2003
git pull && uv sync
```

## 1. Instalar o driver

```bash
uv run epass2003 instalar-driver
```

O comando chama o `sudo` sozinho, se você não for root. Ele:

1. remove o pacote `awp` (driver Oberthur/IDEMIA, que o site da Soluti oferece por engano e que trava o ePass2003);
2. instala `pcscd`, `opensc`, `libccid`, `pcsc-tools` e `libnss3-tools`;
3. baixa o driver oficial da Soluti e confere o SHA-256;
4. instala em `/usr/lib/ePass2003-Linux-x64` (caminho reconhecido pelo Assinador Serpro) e cria `/usr/lib/libcastle.so.1.0.0`;
5. cria uma regra udev para que usuários comuns acessem o token;
6. ativa o `pcscd` e testa a comunicação com o token.

Para conferir manualmente:

```bash
pkcs11-tool --module /usr/lib/libcastle.so.1.0.0 -L
pkcs11-tool --module /usr/lib/libcastle.so.1.0.0 -O --type cert
```

### Configurar navegadores e o Okular

Para que o Firefox, o Chrome/Chromium, o LibreOffice e o Okular enxerguem o token, **feche o Firefox** e rode, sem `sudo`:

```bash
uv run epass2003 configurar-navegadores             # registra o token
uv run epass2003 configurar-navegadores --remover   # desfaz
```

O comando registra o driver em todos os perfis do Firefox (`~/.config/mozilla/firefox` e `~/.mozilla/firefox`) e no `~/.pki/nssdb`, que é usado pelo Chrome/Chromium, pelo LibreOffice e pelo Okular. Ele cria o `~/.pki/nssdb` se for preciso. Cada banco leva uns 20 segundos, porque o driver é carregado a cada operação, e o comando mostra o resultado de cada um. Rodar de novo não duplica nada. Um perfil com o Firefox aberto não é alterado: feche o Firefox e rode outra vez. Reinicie o Chrome e o Okular para que eles vejam o token.

O Firefox Snap não é configurado automaticamente; veja o [guia manual](epass.md).

## 2. Assinar PDFs pela linha de comando

Assinatura simples (invisível); o PIN é pedido no terminal:

```bash
uv run epass2003 assinar documento.pdf
```

O resultado é salvo em `documento-assinado.pdf` (ou no caminho passado em `-o`).

Assinatura visível na primeira página, com rubrica, motivo e local:

```bash
uv run epass2003 assinar documento.pdf -o assinado.pdf \
  --visivel 0,50,50,300,120 \
  --imagem rubrica.png \
  --motivo "Aprovação" --local "Brasília/DF"
```

`--visivel` recebe `PÁGINA,X1,Y1,X2,Y2`: a página começa em 0 e as coordenadas são em pontos (1/72 pol.), com origem no canto inferior esquerdo. Com imagem e texto, a imagem ocupa cerca de 40% à esquerda do retângulo e o texto o restante.

Com carimbo de tempo (RFC 3161):

```bash
uv run epass2003 assinar documento.pdf --tsa http://timestamp.digicert.com
```

Se o token tiver mais de um certificado, por exemplo um vencido e o renovado, é usado o certificado válido que vence por último.

PDFs que já têm assinatura podem ser assinados de novo: a nova assinatura é incremental e recebe um campo próprio (`Assinatura2`, `Assinatura3`...).

### Opções de `assinar`

| Opção | Descrição |
|---|---|
| `-o`, `--saida` | PDF de saída (padrão: `<entrada>-assinado.pdf`) |
| `--modulo` | biblioteca PKCS#11 (padrão: `/usr/lib/libcastle.so.1.0.0` ou, se ausente, `/usr/lib/opensc-pkcs11.so`) |
| `--slot` | número do slot do token |
| `--certificado` | label do certificado a usar, quando o token tiver mais de um |
| `--pin` | PIN do token (também pode vir da variável `EPASS_PIN`; senão é pedido) |
| `--motivo` | motivo da assinatura |
| `--local` | local da assinatura |
| `--tsa` | URL do servidor de carimbo de tempo |
| `--visivel` | cria assinatura visível: `PÁG,X1,Y1,X2,Y2` |
| `--imagem` | imagem (PNG, JPG...) da assinatura visível; exige `--visivel` |
| `--texto` | texto da assinatura visível; aceita `%(signer)s` e `%(ts)s`. Use `''` para mostrar só a imagem |
| `--opacidade` | opacidade da imagem, de 0 a 1 (padrão: 1) |

> Evite `--pin` na linha de comando, pois ele fica no histórico do shell. Prefira digitá-lo quando for pedido ou usar `EPASS_PIN`.

## 3. Assinador local para sites (substituto do assinador do Windows)

Alguns sistemas web assinam PDFs chamando um aplicativo local em `http://localhost:3399/assinarPdf`, disponível apenas para Windows. O `epass2003-assinador` implementa o mesmo protocolo no Linux, com uma janela que só tem o botão **Ligar/Desligar**.

Rode:

```bash
uv run epass2003-assinador            # abre desligado
uv run epass2003-assinador --ligado   # já abre escutando na porta 3399
```

No Ubuntu, se o Qt reclamar do plugin `xcb`, instale `sudo apt install libxcb-cursor0`.

### Atalho no menu

Para abrir o assinador pelo menu de aplicativos, sem terminal, crie o atalho **Assinador ePass2003**:

```bash
uv run epass2003 instalar-atalho             # cria o atalho (só para o seu usuário)
uv run epass2003 instalar-atalho --remover   # remove o atalho
```

O atalho abre o assinador já ligado e aponta para a pasta onde o projeto foi clonado. Se você mover a pasta, rode `instalar-atalho` de novo. Antes de apagá-la, rode `--remover`.

Quando o site pede uma assinatura, o aplicativo baixa o PDF e abre uma janela mostrando o site de origem, o servidor do arquivo e o CPF, com um campo para o PIN do token e o botão **Assinar**. Se o PIN estiver errado, a janela reaparece com um aviso (erros seguidos bloqueiam o token). A janela fecha sozinha se ninguém responder em 5 minutos.

O PDF assinado recebe, na lateral esquerda de todas as páginas e na vertical, o texto **"Assinado eletronicamente por <nome>"**, com o nome do titular do certificado (sem o CPF). O texto entra junto com a assinatura e fica coberto por ela. Se o PDF já tiver alguma assinatura, o texto **não** é impresso, porque alterar as páginas invalidaria as assinaturas anteriores. Assim, num documento com vários signatários, só o primeiro aparece na lateral, e a janela do assinador avisa quando o texto é omitido.

#### Enviar um PDF já assinado (Substituir)

A janela do pedido tem o campo **Ação**:

- **Assinar** (padrão): assina com o token o PDF que o site enviou, como descrito acima.
- **Substituir**: envia ao site um PDF que você já assinou com outra ferramenta, como outro assinador ou outro certificado. Em vez do PIN, clique em **Escolher PDF…**, selecione o arquivo e clique em **Enviar**. O arquivo vai para o site sem nenhuma alteração: sem assinatura nova e sem o texto lateral.

Antes de enviar, o assinador confere que o arquivo é um PDF de até 100 MB com ao menos uma assinatura íntegra (o conteúdo não foi alterado depois de assinado). Se o site informou um CPF, confere também que uma das assinaturas é de um certificado desse CPF. Se o arquivo não passar, a janela reaparece com o motivo. Se o CPF não conferir, o site recebe o mesmo erro de CPF do token.

> **Confira o arquivo antes de enviar:** o assinador não tem como saber se o PDF escolhido é o mesmo documento que o site pediu.

### Protocolo

`GET /assinarPdf?nocache=<ms>&cpf=<base64>&fileDownload=<base64 da URL do PDF>`

| Situação | Resposta (HTTP 200) |
|---|---|
| sucesso | PDF assinado em Base64 (`text/plain`) |
| CPF não corresponde ao certificado do token | JSON `{"status": 500, "message": "..."}` |
| outros erros (cancelado, PIN bloqueado, download falhou...) | JSON `{"status": 400, "message": "..."}` |

O servidor escuta apenas em `127.0.0.1` e responde aos cabeçalhos CORS, inclusive o `Access-Control-Allow-Private-Network` que o Chrome exige para sites da internet acessarem o `localhost`. Uma assinatura é processada por vez.

### Testar sem um sistema web

Para testar o assinador com um PDF do seu computador, abra-o em modo de teste:

```bash
uv run epass2003-assinador --test --ligado
```

Em outro terminal, peça a assinatura:

```bash
uv run epass2003 testar-assinador documento.pdf                    # grava documento-assinado.pdf
uv run epass2003 testar-assinador documento.pdf --cpf 12345678900 -o assinado.pdf
```

O comando faz o mesmo pedido `/assinarPdf` que um site faria. O PDF é entregue ao assinador pelo endpoint `GET /teste/pdf?caminho=<caminho absoluto>`, que só existe no modo de teste. A janela de PIN aparece normalmente, e o comando espera o resultado.

> **Atenção:** enquanto o modo de teste estiver ligado, qualquer site aberto no navegador pode pedir a assinatura de um PDF do seu computador informando o caminho dele. O PDF só sai do computador se você digitar o PIN, e a janela mostra o site que fez o pedido. Use `--test` só para testes, nunca no dia a dia.

## Solução de problemas

- **Token não aparece no `pkcs11-tool`:** replugue o token e rode `sudo systemctl restart pcscd`.
- **Travamentos ou token não reconhecido:** confira se o pacote `awp` não está instalado (`dpkg -s awp`).
- **"Nenhuma biblioteca PKCS#11 encontrada":** rode `uv run epass2003 instalar-driver` ou informe o caminho com `--modulo`.
- **Firefox, Chrome ou Okular não enxergam o token:** rode `uv run epass2003 configurar-navegadores` com o Firefox fechado e reinicie os programas. Para o Firefox Snap, veja o [guia manual](epass.md).

## Desenvolvimento

```bash
uv sync
uv run epass2003 --help
```


# Configurar JSignPdf

Ir no menu File/Preferences, na aba "PKCS#11 provider" colocar o conteúdo abaixo, salvar e reiniciar.


```yaml
name = Castle
library = /usr/lib/libcastle.so
```
